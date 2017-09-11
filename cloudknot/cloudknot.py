from __future__ import absolute_import, division, print_function

import inspect
import operator

from .aws_utils import *
from .due import due, Doi

__all__ = ["CloudKnot"]


# Use duecredit (duecredit.org) to provide a citation to relevant work to
# be cited. This does nothing, unless the user has duecredit installed,
# And calls this with duecredit (as in `python -m duecredit script.py`):
due.cite(Doi(""),
         description="",
         tags=[""],
         path='cloudknot')


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class CloudKnot(object):
    def __init__(self, func, source_file):
        if not (func or source_file):
            raise Exception('you must supply either a user-defined function '
                            'or a source file')
        self.function = function
        self.source_file = source_file

    function = property(operator.attrgetter('_function'))

    @function.setter
    def function(self, f):
        if f:
            if not inspect.isfunction(f):
                raise Exception('if provided, function must be a user-defined '
                                'function')
            self._function = f
        else:
            self._function = None

    source_file = property(operator.attrgetter('_source_file'))

    @source_file.setter
    def source_file(self, fileobj):
        if fileobj:
            self._source_file = fileobj
        else:
            self._source_file = None


class AWSInfrastructure(object):
    def __init__(self, batch_service_role_name='cloudknot-batch-service-role',
                 ecs_instance_role_name='cloudknot-ecs-instance-role',
                 spot_fleet_role_name='cloudknot-spot-fleet-role',
                 vpc_name='cloudknot-vpc',
                 security_group_name='cloudknot-security-group'):
        if not isinstance(batch_service_role_name, str):
            raise Exception('batch_service_role_name must be a string.')

        self._batch_service_role = IamRole(
            name=batch_service_role_name,
            description='This AWS batch service role was automatically '
                        'generated by cloudknot.',
            service='batch',
            policies=('AWSBatchServiceRole',),
            add_instance_role=False
        )

        if not isinstance(ecs_instance_role_name, str):
            raise Exception('ecs_instance_role_name must be a string.')

        self._ecs_instance_role = IamRole(
            name=ecs_instance_role_name,
            description='This AWS ECS instance role was automatically '
                        'generated by cloudknot.',
            service='ec2',
            policies=('AmazonEC2ContainerServiceforEC2Role',),
            add_instance_role=True
        )

        if not isinstance(spot_fleet_role_name, str):
            raise Exception('spot_fleet_role_name must be a string.')

        self._spot_fleet_role = IamRole(
            name=spot_fleet_role_name,
            description='This AWS spot fleet role was automatically '
                        'generated by cloudknot.',
            service='spotfleet',
            policies=('AmazonEC2SpotFleetRole',),
            add_instance_role=False
        )

        if not isinstance(vpc_name, str):
            raise Exception('vpc_name must be a string')

        self._vpc = Vpc(name=vpc_name)
        self._security_group = SecurityGroup(
            name=security_group_name,
            vpc=self.vpc
        )

    batch_service_role = property(operator.attrgetter('_batch_service_role'))
    ecs_instance_role = property(operator.attrgetter('_ecs_instance_role'))
    spot_fleet_role = property(operator.attrgetter('_spot_fleet_role'))
    vpc = property(operator.attrgetter('_vpc'))
    security_group = property(operator.attrgetter('_security_group'))


class AWSPipeline(object):
    def __init__(self, infrastructure,
                 docker_image_name='cloudknot-docker-image',
                 job_definition_name='cloudknot-job-definition',
                 compute_environment_name='cloudknot-compute-environment',
                 job_queue_name='cloudknot-job-queue', vcpus=1, memory=32000):
        if not isinstance(infrastructure, AWSInfrastructure):
            raise Exception('infrastructure must be an AWSInfrastructure '
                            'instance.')

        self._infrastructure = infrastructure

        if not isinstance(docker_image_name, str):
            raise Exception('docker_image_name must be a string.')

        if not isinstance(job_definition_name, str):
            raise Exception('job_definition_name must be a string.')

        if not isinstance(compute_environment_name, str):
            raise Exception('compute_environment_name must be a string.')

        if not isinstance(job_queue_name, str):
            raise Exception('job_queue_name must be a string.')

        try:
            cpus = int(vcpus)
            if cpus < 1:
                raise Exception('vcpus must be positive')
        except ValueError:
            raise Exception('vcpus must be an integer')

        try:
            mem = int(memory)
            if mem < 1:
                raise Exception('memory must be positive')
        except ValueError:
            raise Exception('memory must be an integer')

        # WIP
        self._docker_image = DockerImage(
            name=docker_image_name#,
            #build_path=,
            #dockerfile=,
            #requirements=
        )

        self._job_definition = JobDefinition(
            name=job_definition_name,
            job_role=self._infrastructure.ecs_instance_role,
            docker_image=self._docker_image.uri,
            vcpus=cpus,
            memory=mem
        )

        self._compute_environment = ComputeEnvironment(
            name=compute_environment_name,
            batch_service_role=self._infrastructure.batch_service_role,
            instance_role=self._infrastructure.ecs_instance_role,
            vpc=self._infrastructure.vpc,
            security_group=self._infrastructure.security_group,
            desired_vcpus=cpus
        )

        self._job_queue = JobQueue(
            name=job_queue_name,
            compute_environments=self._compute_environment
        )

    infrastructure = property(operator.attrgetter('_infrastructure'))
    docker_image = property(operator.attrgetter('_docker_image'))
    job_definition = property(operator.attrgetter('_job_definition'))
    job_queue = property(operator.attrgetter('_job_queue'))
    compute_environment = property(operator.attrgetter('_compute_environment'))
