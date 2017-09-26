import boto3
import logging
import operator
import sys
import time

from ..config import get_default_region

__all__ = ["NamedObject", "ObjectWithArn",
           "ObjectWithUsernameAndMemory", "IAM", "EC2", "ECR", "BATCH",
           "wait_for_compute_environment", "wait_for_job_queue"]

IAM = boto3.client('iam', region_name=get_default_region())
EC2 = boto3.client('ec2', region_name=get_default_region())
BATCH = boto3.client('batch', region_name=get_default_region())
ECR = boto3.client('ecr', region_name=get_default_region())


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class ResourceExistsException(Exception):
    def __init__(self, message, resource_id):
        super(ResourceExistsException, self).__init__(message)
        self.resource_id = resource_id


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class ResourceDoesNotExistException(Exception):
    def __init__(self, message, resource_id):
        super(ResourceDoesNotExistException, self).__init__(message)
        self.resource_id = resource_id


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class CannotDeleteResourceException(Exception):
    def __init__(self, message, resource_id):
        super(CannotDeleteResourceException, self).__init__(message)
        self.resource_id = resource_id


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class NamedObject(object):
    """Base class for building objects with name property"""
    def __init__(self, name):
        """ Initialize a base class with a name

        Parameters
        ----------
        name : string
            Name of the object
        """
        self._name = str(name)

    name = property(operator.attrgetter('_name'))


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class ObjectWithArn(NamedObject):
    """ Base class for building objects with an Amazon Resource Name (ARN)
    Inherits from NamedObject
    """
    def __init__(self, name):
        """ Initialize a base class with name and Amazon Resource Number (ARN)

        Parameters
        ----------
        name : string
            Name of the object
        """
        super(ObjectWithArn, self).__init__(name=name)
        self._arn = None

    @property
    def arn(self):
        return self._arn


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class ObjectWithUsernameAndMemory(ObjectWithArn):
    """ Base class for building objects with properties memory and username
    Inherits from ObjectWithArn
    """
    def __init__(self, name, memory=32000, username='cloudknot-user'):
        """ Initialize a base class with name, memory, and username properties

        Parameters
        ----------
        name : string
            Name of the object

        memory : int
            memory (MiB) to be used for this job definition
            Default: 32000

        username : string
            username for be used for this job definition
            Default: cloudknot-user
        """
        super(ObjectWithUsernameAndMemory, self).__init__(name=name)

        try:
            mem = int(memory)
            if mem < 1:
                raise ValueError('memory must be positive')
            else:
                self._memory = mem
        except ValueError:
            raise ValueError('memory must be an integer')

        self._username = str(username)

    memory = property(operator.attrgetter('_memory'))
    username = property(operator.attrgetter('_username'))


# noinspection PyPropertyAccess,PyAttributeOutsideInit
def wait_for_compute_environment(arn, name, log=True, max_wait_time=60):
    # Wait for compute environment to finish modifying
    waiting = True
    num_waits = 0
    while waiting:
        if log:
            logging.info(
                'Waiting for AWS to finish modifying compute environment '
                '{name:s}.'.format(name=name)
            )

        response = BATCH.describe_compute_environments(
            computeEnvironments=[arn]
        )

        waiting = (response.get('computeEnvironments')[0]['status']
                   in ['CREATING', 'UPDATING']
                   or response.get('computeEnvironments') == [])

        time.sleep(1)
        num_waits += 1
        if num_waits > max_wait_time:
            sys.exit('Waiting too long for AWS to modify compute '
                     'environment. Aborting.')


# noinspection PyPropertyAccess,PyAttributeOutsideInit
def wait_for_job_queue(name, log=True, max_wait_time=60):
    # Wait for job queue to be in DISABLED state
    waiting = True
    num_waits = 0
    while waiting:
        if log:
            logging.info(
                'Waiting for AWS to finish modifying job queue '
                '{name:s}.'.format(name=name)
            )

        response = BATCH.describe_job_queues(jobQueues=[name])
        waiting = (response.get('jobQueues')[0]['status']
                   in ['CREATING', 'UPDATING'])

        time.sleep(1)
        num_waits += 1
        if num_waits > max_wait_time:
            sys.exit('Waiting too long for AWS to modify job queue. '
                     'Aborting.')
