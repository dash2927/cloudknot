from __future__ import absolute_import, division, print_function

import configparser
import logging
import operator
import six

from . import aws
from .config import get_config_file
from . import dockerimage

__all__ = ["Pars", "Knot"]

mod_logger = logging.getLogger(__name__)


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class Pars(aws.NamedObject):
    """PARS stands for Persistent AWS Resource Set

    This object collects AWS resources that could, in theory, be created only
    once for each cloudknot user and used for all of their subsequent AWS
    batch jobs. This set consists of IAM roles, a VPC with subnets for each
    availability zone, and a security group.
    """
    def __init__(self, name='default',
                 batch_service_role_name=None, ecs_instance_role_name=None,
                 ecs_task_role_name=None, spot_fleet_role_name=None,
                 policies=(), vpc_id=None, vpc_name=None, use_default_vpc=True,
                 security_group_id=None, security_group_name=None):
        """Initialize a PARS instance.

        Parameters
        ----------
        name : str
            The name of this PARS. If `pars name` exists in the config file,
            Pars will retrieve those PARS resource parameters. Otherwise,
            Pars will create a new PARS with this name.
            Default: 'default'

        batch_service_role_name : str
            Name of this PARS' batch service IAM role. If the role already
            exists, Pars will adopt it. Otherwise, it will create it.
            Default: name + '-cloudknot-batch-service-role'

        ecs_instance_role_name : str
            Name of this PARS' ECS instance IAM role. If the role already
            exists, Pars will adopt it. Otherwise, it will create it.
            Default: name + '-cloudknot-ecs-instance-role'

        ecs_task_role_name : str
            Name of this PARS' ECS task IAM role. If the role already
            exists, Pars will adopt it. Otherwise, it will create it.
            Default: name + '-cloudknot-ecs-task-role'

        spot_fleet_role_name : str
            Name of this PARS' spot fleet IAM role. If the role already
            exists, Pars will adopt it. Otherwise, it will create it.
            Default: name + '-cloudknot-spot-fleet-role'

        policies : tuple of strings
            tuple of names of AWS policies to attach to each role
            Default: ()

        vpc_id : str
            The VPC-ID of the pre-existing VPC that this PARS should adopt
            Default: None

        vpc_name : str
            The name of the VPC that this PARS should create
            Default: name + '-cloudknot-vpc'

        use_default_vpc : bool
            if True, create or retrieve the default VPC
            if False, use other input args to create a non-default VPC

        security_group_id : str
            The ID of the pre-existing security group that this PARS should
            adopt
            Default: None

        security_group_name : str
            The name of the security group that this PARS should create
            Default: name + '-cloudknot-security-group'
        """
        # Validate name input
        if not isinstance(name, six.string_types):
            raise ValueError('PARS name must be a string. You passed a '
                             '{t!s}'.format(t=type(name)))

        super(Pars, self).__init__(name=name)

        # Validate vpc_name input
        if vpc_name:
            if not isinstance(vpc_name, six.string_types):
                raise ValueError('if provided, vpc_name must be a string.')
        else:
            vpc_name = name + '-cloudknot-vpc'

        # Validate security_group_name input
        if security_group_name:
            if not isinstance(security_group_name, six.string_types):
                raise ValueError('if provided, security_group_name must be '
                                 'a string.')
        else:
            security_group_name = name + '-cloudknot-security-group'

        # Check for existence of this pars in the config file
        config = configparser.ConfigParser()
        config.read(get_config_file())
        self._pars_name = 'pars ' + self.name
        if self._pars_name in config.sections():
            self._region = config.get(self._pars_name, 'region')
            self._profile = config.get(self._pars_name, 'profile')
            self.check_profile_and_region()

            # Pars exists, check that user did not provide any resource names
            if any([batch_service_role_name, ecs_instance_role_name,
                    spot_fleet_role_name, vpc_id, security_group_id]):
                raise ValueError('You provided resources for a pars that '
                                 'already exists in configuration file '
                                 '{fn:s}.'.format(fn=get_config_file()))

            mod_logger.info('Found PARS {name:s} in config'.format(name=name))
            role_name = config.get(self._pars_name, 'batch-service-role')
            try:
                # Use config values to adopt role if it exists already
                self._batch_service_role = aws.IamRole(name=role_name)
                mod_logger.info('PARS {name:s} adopted role {role:s}'.format(
                    name=name, role=role_name
                ))
            except aws.ResourceDoesNotExistException:
                # Otherwise create the new role
                self._batch_service_role = aws.IamRole(
                    name=role_name,
                    description='This AWS batch service role was '
                                'automatically generated by cloudknot.',
                    service='batch',
                    policies=('AWSBatchServiceRole',) + policies,
                    add_instance_profile=False
                )
                mod_logger.info('PARS {name:s} created role {role:s}'.format(
                    name=name, role=role_name
                ))

            role_name = config.get(self._pars_name, 'ecs-instance-role')
            try:
                # Use config values to adopt role if it exists already
                self._ecs_instance_role = aws.IamRole(name=role_name)
                mod_logger.info('PARS {name:s} adopted role {role:s}'.format(
                    name=name, role=role_name
                ))
            except aws.ResourceDoesNotExistException:
                # Otherwise create the new role
                pols = ('AmazonEC2ContainerServiceforEC2Role',) + policies
                self._ecs_instance_role = aws.IamRole(
                    name=role_name,
                    description='This AWS ECS instance role was automatically '
                                'generated by cloudknot.',
                    service='ec2',
                    policies=pols,
                    add_instance_profile=True
                )
                mod_logger.info('PARS {name:s} created role {role:s}'.format(
                    name=name, role=role_name
                ))

            role_name = config.get(self._pars_name, 'ecs-task-role')
            try:
                # Use config values to adopt role if it exists already
                self._ecs_task_role = aws.IamRole(name=role_name)
                mod_logger.info('PARS {name:s} adopted role {role:s}'.format(
                    name=name, role=role_name
                ))
            except aws.ResourceDoesNotExistException:
                # Otherwise create the new role
                self._ecs_task_role = aws.IamRole(
                    name=role_name,
                    description='This AWS ECS task role was automatically '
                                'generated by cloudknot.',
                    service='ecs-tasks',
                    policies=policies,
                    add_instance_profile=True
                )
                mod_logger.info('PARS {name:s} created role {role:s}'.format(
                    name=name, role=role_name
                ))

            role_name = config.get(self._pars_name, 'spot-fleet-role')
            try:
                # Use config values to adopt role if it exists already
                self._spot_fleet_role = aws.IamRole(name=role_name)
                mod_logger.info('PARS {name:s} adopted role {role:s}'.format(
                    name=name, role=role_name
                ))
            except aws.ResourceDoesNotExistException:
                # Otherwise create the new role
                self._spot_fleet_role = aws.IamRole(
                    name=role_name,
                    description='This AWS spot fleet role was automatically '
                                'generated by cloudknot.',
                    service='spotfleet',
                    policies=('AmazonEC2SpotFleetRole',) + policies,
                    add_instance_profile=False
                )
                mod_logger.info('PARS {name:s} created role {role:s}'.format(
                    name=name, role=role_name
                ))

            try:
                # Use config values to adopt VPC if it exists already
                vpcid = config.get(self._pars_name, 'vpc')
                self._vpc = aws.Vpc(vpc_id=vpcid)
                mod_logger.info('PARS {name:s} adopted VPC {vpcid:s}'.format(
                    name=name, vpcid=vpcid
                ))
            except aws.ResourceDoesNotExistException:
                # Otherwise create the new VPC
                if use_default_vpc:
                    try:
                        self._vpc = aws.Vpc(use_default_vpc=True)
                    except aws.CannotCreateResourceException:
                        self._vpc = aws.Vpc(name=vpc_name)
                else:
                    self._vpc = aws.Vpc(name=vpc_name)
                config = configparser.ConfigParser()
                config.read(get_config_file())
                config.set(self._pars_name, 'vpc', self.vpc.vpc_id)
                with open(get_config_file(), 'w') as f:
                    config.write(f)
                mod_logger.info('PARS {name:s} created VPC {vpcid:s}'.format(
                    name=name, vpcid=self.vpc.vpc_id
                ))

            try:
                # Use config values to adopt security group if it exists
                sgid = config.get(self._pars_name, 'security-group')
                self._security_group = aws.SecurityGroup(
                    security_group_id=sgid
                )
                mod_logger.info(
                    'PARS {name:s} adopted security group {sgid:s}'.format(
                        name=name, sgid=sgid
                    )
                )
            except aws.ResourceDoesNotExistException:
                # Otherwise create the new security group
                self._security_group = aws.SecurityGroup(
                    name=security_group_name,
                    vpc=self._vpc
                )
                config = configparser.ConfigParser()
                config.read(get_config_file())
                config.set(
                    self._pars_name,
                    'security-group', self.security_group.security_group_id
                )
                with open(get_config_file(), 'w') as f:
                    config.write(f)
                mod_logger.info(
                    'PARS {name:s} created security group {sgid:s}'.format(
                        name=name, sgid=self.security_group.security_group_id
                    )
                )

            config = configparser.ConfigParser()
            config.read(get_config_file())
            config.set(self._pars_name, 'region', self.region)
            config.set(self._pars_name, 'profile', self.profile)

            # Save config to file
            with open(get_config_file(), 'w') as f:
                config.write(f)
        else:
            # Pars doesn't exist, use input names to adopt/create resources
            # Validate role name input
            if batch_service_role_name:
                if not isinstance(batch_service_role_name, six.string_types):
                    raise ValueError('if provided, batch_service_role_name '
                                     'must be a string.')
            else:
                batch_service_role_name = (
                    name + '-cloudknot-batch-service-role'
                )

            try:
                # Create new role
                self._batch_service_role = aws.IamRole(
                    name=batch_service_role_name,
                    description='This AWS batch service role was '
                                'automatically generated by cloudknot.',
                    service='batch',
                    policies=('AWSBatchServiceRole',) + policies,
                    add_instance_profile=False
                )
                mod_logger.info('PARS {name:s} created role {role:s}'.format(
                    name=name, role=batch_service_role_name
                ))
            except aws.ResourceExistsException as e:
                # If it already exists, simply adopt it
                self._batch_service_role = aws.IamRole(name=e.resource_id)
                mod_logger.info('PARS {name:s} adopted role {role:s}'.format(
                    name=name, role=e.resource_id
                ))

            # Validate role name input
            if ecs_instance_role_name:
                if not isinstance(ecs_instance_role_name, six.string_types):
                    # Clean up after ourselves and raise ValueError
                    self.batch_service_role.clobber()
                    raise ValueError('if provided, ecs_instance_role_name '
                                     'must be a string.')
            else:
                ecs_instance_role_name = name + '-cloudknot-ecs-instance-role'

            try:
                # Create new role
                pols = ('AmazonEC2ContainerServiceforEC2Role',) + policies
                self._ecs_instance_role = aws.IamRole(
                    name=ecs_instance_role_name,
                    description='This AWS ECS instance role was automatically '
                                'generated by cloudknot.',
                    service='ec2',
                    policies=pols,
                    add_instance_profile=True
                )
                mod_logger.info('PARS {name:s} created role {role:s}'.format(
                    name=name, role=ecs_instance_role_name
                ))
            except aws.ResourceExistsException as e:
                # If it already exists, simply adopt it
                self._ecs_instance_role = aws.IamRole(name=e.resource_id)
                mod_logger.info('PARS {name:s} adopted role {role:s}'.format(
                    name=name, role=e.resource_id
                ))

            # Validate role name input
            if ecs_task_role_name:
                if not isinstance(ecs_task_role_name, six.string_types):
                    # Clean up after ourselves and raise ValueError
                    self.batch_service_role.clobber()
                    self.ecs_instance_role.clobber()
                    raise ValueError('if provided, ecs_instance_role_name '
                                     'must be a string.')
            else:
                ecs_task_role_name = name + '-cloudknot-ecs-task-role'

            try:
                # Create new role
                self._ecs_task_role = aws.IamRole(
                    name=ecs_task_role_name,
                    description='This AWS ECS task role was automatically '
                                'generated by cloudknot.',
                    service='ecs-tasks',
                    policies=policies,
                    add_instance_profile=False
                )
                mod_logger.info('PARS {name:s} created role {role:s}'.format(
                    name=name, role=ecs_task_role_name
                ))
            except aws.ResourceExistsException as e:
                # If it already exists, simply adopt it
                self._ecs_task_role = aws.IamRole(name=e.resource_id)
                mod_logger.info('PARS {name:s} adopted role {role:s}'.format(
                    name=name, role=e.resource_id
                ))

            # Validate role name input
            if spot_fleet_role_name:
                if not isinstance(spot_fleet_role_name, six.string_types):
                    # Clean up after ourselves and raise ValueError
                    self.batch_service_role.clobber()
                    self.ecs_instance_role.clobber()
                    self.ecs_task_role.clobber()
                    raise ValueError('if provided, spot_fleet_role_name must '
                                     'be a string.')
            else:
                spot_fleet_role_name = name + '-cloudknot-spot-fleet-role'

            try:
                # Create new role
                self._spot_fleet_role = aws.IamRole(
                    name=spot_fleet_role_name,
                    description='This AWS spot fleet role was automatically '
                                'generated by cloudknot.',
                    service='spotfleet',
                    policies=('AmazonEC2SpotFleetRole',) + policies,
                    add_instance_profile=False
                )
                mod_logger.info('PARS {name:s} created role {role:s}'.format(
                    name=name, role=spot_fleet_role_name
                ))
            except aws.ResourceExistsException as e:
                # If it already exists, simply adopt it
                self._spot_fleet_role = aws.IamRole(name=e.resource_id)
                mod_logger.info('PARS {name:s} adopted role {role:s}'.format(
                    name=name, role=e.resource_id
                ))

            if vpc_id:
                # Validate vpc_id input
                if not isinstance(vpc_id, six.string_types):
                    # Clean up after ourselves and raise ValueError
                    self.batch_service_role.clobber()
                    self.ecs_instance_role.clobber()
                    self.ecs_task_role.clobber()
                    self.spot_fleet_role.clobber()
                    raise ValueError('if provided, vpc_id must be a string')

                # Adopt the VPC
                self._vpc = aws.Vpc(vpc_id=vpc_id)
                mod_logger.info('PARS {name:s} adopted VPC {vpcid:s}'.format(
                    name=name, vpcid=vpc_id
                ))
            else:
                try:
                    if use_default_vpc:
                        try:
                            self._vpc = aws.Vpc(use_default_vpc=True)
                        except aws.CannotCreateResourceException:
                            self._vpc = aws.Vpc(name=vpc_name)
                    else:
                        self._vpc = aws.Vpc(name=vpc_name)

                    mod_logger.info(
                        'PARS {name:s} created VPC {vpcid:s}'.format(
                            name=name, vpcid=self.vpc.vpc_id
                        )
                    )
                except aws.ResourceExistsException as e:
                    # If it already exists, simply adopt it
                    self._vpc = aws.Vpc(vpc_id=e.resource_id)
                    mod_logger.info(
                        'PARS {name:s} adopted VPC {vpcid:s}'.format(
                            name=name, vpcid=e.resource_id
                        )
                    )

            if security_group_id:
                # Validate security_group_id input
                if not isinstance(security_group_id, six.string_types):
                    # Clean up after ourselves and raise ValueError
                    self.batch_service_role.clobber()
                    self.ecs_instance_role.clobber()
                    self.ecs_task_role.clobber()
                    self.spot_fleet_role.clobber()
                    self.vpc.clobber()
                    raise ValueError('if provided, security_group_id must '
                                     'be a string')

                # Adopt the security group
                self._security_group = aws.SecurityGroup(
                    security_group_id=security_group_id
                )
                mod_logger.info(
                    'PARS {name:s} adopted security group {sgid:s}'.format(
                        name=name, sgid=security_group_id
                    )
                )
            else:
                try:
                    # Create new security group
                    self._security_group = aws.SecurityGroup(
                        name=security_group_name,
                        vpc=self.vpc
                    )
                    mod_logger.info(
                        'PARS {name:s} created security group {sgid:s}'.format(
                            name=name,
                            sgid=self.security_group.security_group_id
                        )
                    )
                except aws.ResourceExistsException as e:
                    # If it already exists, simply adopt it
                    self._security_group = aws.SecurityGroup(
                        security_group_id=e.resource_id
                    )
                    mod_logger.info(
                        'PARS {name:s} adopted security group {sgid:s}'.format(
                            name=name, sgid=e.resource_id
                        )
                    )

            # Save the new pars resources in config object
            # Use config.set() for python 2.7 compatibility
            config = configparser.ConfigParser()
            config.read(get_config_file())
            config.add_section(self._pars_name)
            config.set(self._pars_name, 'region', self.region)
            config.set(self._pars_name, 'profile', self.profile)
            config.set(
                self._pars_name,
                'batch-service-role', self._batch_service_role.name
            )
            config.set(
                self._pars_name,
                'ecs-instance-role', self._ecs_instance_role.name
            )
            config.set(
                self._pars_name,
                'ecs-task-role', self._ecs_task_role.name
            )
            config.set(
                self._pars_name, 'spot-fleet-role', self._spot_fleet_role.name
            )
            config.set(self._pars_name, 'vpc', self._vpc.vpc_id)
            config.set(
                self._pars_name,
                'security-group', self._security_group.security_group_id
            )

            # Save config to file
            with open(get_config_file(), 'w') as f:
                config.write(f)

    @property
    def pars_name(self):
        """The section name for this PARS in the cloudknot config file"""
        return self._pars_name

    @staticmethod
    def _role_setter(attr):
        """Static method to return setter methods for new IamRoles"""
        def set_role(self, new_role):
            """Setter method to attach new IAM role to this PARS

            This method clobbers the old role and adopts the new one.

            Parameters
            ----------
            new_role :
                new IamRole instance to attach to this Pars

            Returns
            -------
            None
            """
            if self.clobbered:
                raise aws.ResourceClobberedException(
                    'This PARS has already been clobbered.',
                    self.name
                )

            # Verify input
            if not isinstance(new_role, aws.IamRole):
                raise ValueError('new role must be an instance of IamRole')

            old_role = getattr(self, attr)

            if old_role.profile != new_role.profile:
                raise aws.ProfileException(new_role.profile)

            mod_logger.warning(
                'You are setting a new role for PARS {name:s}. The old '
                'role {role_name:s} will be clobbered.'.format(
                    name=self.name, role_name=old_role.name
                )
            )

            # Delete the old role
            old_role.clobber()

            # Set the new role attribute
            setattr(self, attr, new_role)

            # Replace the appropriate line in the config file
            config = configparser.ConfigParser()
            config.read(get_config_file())
            field_name = attr.lstrip('_').replace('_', '-')
            config.set(self._pars_name, field_name, new_role.name)
            with open(get_config_file(), 'w') as f:
                config.write(f)

            mod_logger.info(
                'PARS {name:s} adopted new role {role_name:s}'.format(
                    name=self.name, role_name=new_role.name
                )
            )

        return set_role

    batch_service_role = property(
        fget=operator.attrgetter('_batch_service_role'),
        fset=_role_setter.__func__('_batch_service_role')
    )
    ecs_instance_role = property(
        fget=operator.attrgetter('_ecs_instance_role'),
        fset=_role_setter.__func__('_ecs_instance_role')
    )
    ecs_task_role = property(
        fget=operator.attrgetter('_ecs_task_role'),
        fset=_role_setter.__func__('_ecs_task_role')
    )
    spot_fleet_role = property(
        fget=operator.attrgetter('_spot_fleet_role'),
        fset=_role_setter.__func__('_spot_fleet_role')
    )

    @property
    def vpc(self):
        """The Vpc instance attached to this PARS"""
        return self._vpc

    @vpc.setter
    def vpc(self, v):
        """Setter method to attach new VPC to this PARS

        This method clobbers the old VPC and adopts the new one.

        Parameters
        ----------
        v : Vpc
            new Vpc instance to attach to this Pars

        Returns
        -------
        None
        """
        if self.clobbered:
            raise aws.ResourceClobberedException(
                'This PARS has already been clobbered.',
                self.name
            )

        if not isinstance(v, aws.Vpc):
            raise ValueError('new vpc must be an instance of Vpc')

        if v.region != self._vpc.region:
            raise aws.RegionException(v.region)

        if v.profile != self._vpc.profile:
            raise aws.ProfileException(v.profile)

        mod_logger.warning(
            'You are setting a new VPC for PARS {name:s}. The old '
            'VPC {vpc_id:s} will be clobbered.'.format(
                name=self.name, vpc_id=self.vpc.vpc_id
            )
        )

        # We have to replace the security group too, since it depends on the
        # VPC. Create a new security group based on the new VPC but with the
        # old name and description.
        sg_name = self.security_group.name
        sg_desc = self.security_group.description

        # The security group setter method will take care of clobbering the
        # old security group and updating config, etc.
        self.security_group = aws.SecurityGroup(
            name=sg_name, vpc=v, description=sg_desc
        )

        if not self._vpc.is_default:
            self._vpc.clobber()

        self._vpc = v

        # Replace the appropriate line in the config file
        config = configparser.ConfigParser()
        config.read(get_config_file())
        config.set(self._pars_name, 'vpc', v.vpc_id)
        with open(get_config_file(), 'w') as f:
            config.write(f)

        mod_logger.info(
            'PARS {name:s} adopted new VPC {vpcid:s}'.format(
                name=self.name, vpcid=self.vpc.vpc_id
            )
        )

    @property
    def security_group(self):
        """The SecurityGroup instance attached to this PARS"""
        return self._security_group

    @security_group.setter
    def security_group(self, sg):
        """Setter method to attach new security group to this PARS

        This method clobbers the old security group and adopts the new one.

        Parameters
        ----------
        sg : SecurityGroup
            new SecurityGroup instance to attach to this Pars

        Returns
        -------
        None
        """
        if self.clobbered:
            raise aws.ResourceClobberedException(
                'This PARS has already been clobbered.',
                self.name
            )

        if not isinstance(sg, aws.SecurityGroup):
            raise ValueError('new security group must be an instance of '
                             'SecurityGroup')

        if sg.region != self._security_group.region:
            raise aws.RegionException(sg.region)

        if sg.profile != self._security_group.profile:
            raise aws.ProfileException(sg.profile)

        mod_logger.warning(
            'You are setting a new security group for PARS {name:s}. The old '
            'security group {sg_id:s} will be clobbered.'.format(
                name=self.name, sg_id=self.security_group.security_group_id
            )
        )
        old_sg = self._security_group
        old_sg.clobber()
        self._security_group = sg

        # Replace the appropriate line in the config file
        config = configparser.ConfigParser()
        config.read(get_config_file())
        config.set(self._pars_name, 'security-group', sg.security_group_id)
        with open(get_config_file(), 'w') as f:
            config.write(f)

        mod_logger.info(
            'PARS {name:s} adopted new security group {sgid:s}'.format(
                name=self.name, sgid=sg.security_group_id
            )
        )

    def clobber(self):
        """Delete associated AWS resources and remove section from config"""
        if self.clobbered:
            return

        self.check_profile_and_region()

        # Delete all associated AWS resources
        self._security_group.clobber()
        self._vpc.clobber()
        self._spot_fleet_role.clobber()
        self._ecs_task_role.clobber()
        self._ecs_instance_role.clobber()
        self._batch_service_role.clobber()

        # Remove this section from the config file
        config = configparser.ConfigParser()
        config.read(get_config_file())
        config.remove_section(self._pars_name)
        with open(get_config_file(), 'w') as f:
            config.write(f)

        # Set the clobbered parameter to True,
        # preventing subsequent method calls
        self._clobbered = True

        mod_logger.info('Clobbered PARS {name:s}'.format(name=self.name))


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class Knot(aws.NamedObject):
    """A collection of resources and methods to submit jobs to AWS Batch

    This object collects AWS resources that should be created once for each
    type of batch run. The resource set consists of a PARS; a docker image
    made from an input function or python script; a remote docker repo to
    house said image; and an AWS batch job definition, compute environment,
    and job queue. It also contains methods to submit batch jobs for a range
    of arguments.
    """
    def __init__(self, name='default', pars=None, pars_policies=(),
                 docker_image=None, func=None, image_script_path=None,
                 image_work_dir=None, username=None, repo_name=None,
                 image_tags=None, job_definition_name=None,
                 job_def_vcpus=None, memory=None,
                 retries=None, compute_environment_name=None,
                 instance_types=None, resource_type=None, min_vcpus=None,
                 max_vcpus=None, desired_vcpus=None, image_id=None,
                 ec2_key_pair=None, ce_tags=None, bid_percentage=None,
                 job_queue_name=None, priority=None):
        """Initialize a Knot instance

        Parameters
        ----------
        name : str, optional
            The name for this knot
            Default='default'

        pars : Pars, optional
            The PARS on which to base this knot's AWS resources
            Default: instance returned by Pars()

        pars_policies : tuple of strings
            tuple of names of AWS policies to attach to each role
            Default: ()

        docker_image : DockerImage, optional
            The pre-existing DockerImage instance to adopt

        func : function
            Python function to be dockerized

        image_script_path : str
            Path to file with python script to be dockerized

        image_work_dir : string
            Directory to store Dockerfile, requirements.txt, and python
            script with CLI
            Default: parent directory of script if `script_path` is provided
            else DockerImage creates a new directory, accessible by the
            `docker_image.build_path` property.

        username : string
            default username created in Dockerfile and in batch job definition
            Default: 'cloudknot-user'

        repo_name : str, optional
            Name of the AWS ECR repository to store the created Docker image
            Default: 'cloudknot/' + self.docker_image.images[0]['name']

        image_tags : str or sequence of str
            Tags to be applied to this Docker image

        job_definition_name : str, optional
            Name for this knot's AWS Batch job definition
            Default: name + '-cloudknot-compute-environment'

        job_def_vcpus : int, optional
            number of virtual cpus to be used to this knot's job definition
            Default: 1

        memory : int, optional
            memory (MiB) to be used for this knot's job definition
            Default: 8000

        retries : int, optional
            number of times a job can be moved to 'RUNNABLE' status.
            May be between 1 and 10
            Default: 3

        compute_environment_name : str
            Name for this knot's AWS Batch compute environment
            Default: name + '-cloudknot-compute-environment'

        instance_types : string or sequence of strings, optional
            Compute environment instance types
            Default: ('optimal',)

        resource_type : 'EC2' or 'SPOT'
            Compute environment resource type, either "EC2" or "SPOT"
            Default: 'EC2'

        min_vcpus : int, optional
            minimum number of virtual cpus for instances launched in this
            compute environment
            Default: 0

        max_vcpus : int, optional
            maximum number of virtual cpus for instances launched in this
            compute environment
            Default: 256

        desired_vcpus : int, optional
            desired number of virtual cpus for instances launched in this
            compute environment
            Default: 8

        image_id : string or None, optional
            optional AMI id used for instances launched in this compute
            environment
            Default: None

        ec2_key_pair : string or None, optional
            optional EC2 key pair used for instances launched in this compute
            environment
            Default: None

        tags : dictionary or None, optional
            optional key-value pair tags to be applied to resources in this
            compute environment
            Default: None

        bid_percentage : int, optional
            Compute environment bid percentage if using spot instances
            Default: 50

        job_queue_name : str, optional
            Name for this knot's AWS Batch job queue
            Default: name + '-cloudknot-job-queue'

        priority : int, optional
            Default priority for jobs in this knot's job queue
            Default: 1
        """
        # Validate name input
        if not isinstance(name, six.string_types):
            raise ValueError('Knot name must be a string. You passed a '
                             '{t!s}'.format(t=type(name)))

        super(Knot, self).__init__(name=name)
        self._knot_name = 'knot ' + name

        image_tags = image_tags if image_tags else ['cloudknot']

        # Check for existence of this pars in the config file
        config = configparser.ConfigParser()
        config.read(get_config_file())
        if self._knot_name in config.sections():
            if any([
                pars, pars_policies, docker_image, func, image_script_path,
                image_work_dir, username, repo_name, job_definition_name,
                job_def_vcpus, memory, retries, compute_environment_name,
                instance_types, resource_type, min_vcpus, max_vcpus,
                desired_vcpus, image_id, ec2_key_pair, ce_tags, bid_percentage,
                job_queue_name, priority
            ]):
                raise ValueError('You specified configuration arguments for '
                                 'a knot that already exists. To create a '
                                 'new knot, please choose a new name or '
                                 'clobber the pre-existing knot.')

            mod_logger.info('Found knot {name:s} in config'.format(name=name))

            self._region = config.get(self._knot_name, 'region')
            self._profile = config.get(self._knot_name, 'profile')
            self.check_profile_and_region()

            pars_name = config.get(self._knot_name, 'pars')
            self._pars = Pars(name=pars_name)
            mod_logger.info('Knot {name:s} adopted PARS '
                            '{p:s}'.format(name=self.name, p=self.pars.name))

            image_name = config.get(self._knot_name, 'docker-image')
            self._docker_image = dockerimage.DockerImage(name=image_name)
            mod_logger.info('Knot {name:s} adopted docker image {dr:s}'
                            ''.format(name=self.name, dr=image_name))

            if not self.docker_image.images:
                self.docker_image.build(tags=image_tags)
                mod_logger.info(
                    'knot {name:s} built docker image {i!s}'
                    ''.format(name=self.name, i=self.docker_image.images)
                )

            if self.docker_image.repo_uri is None:
                repo_name = config.get(self._knot_name, 'docker-repo')
                self._docker_repo = aws.DockerRepo(name=repo_name)
                mod_logger.info('Knot {name:s} adopted docker repository '
                                '{dr:s}'.format(name=self.name, dr=repo_name))

                self.docker_image.push(repo=self.docker_repo)
                mod_logger.info(
                    'Knot {name:s} pushed docker image {dr:s}'
                    ''.format(name=self.name, dr=self.docker_image.name)
                )
            else:
                self._docker_repo = None

            jd_name = config.get(self._knot_name, 'job-definition')
            self._job_definition = aws.JobDefinition(name=jd_name)
            mod_logger.info('Knot {name:s} adopted job definition '
                            '{jd:s}'.format(name=self.name, jd=jd_name))

            ce_name = config.get(self._knot_name, 'compute-environment')
            self._compute_environment = aws.ComputeEnvironment(name=ce_name)
            mod_logger.info('Knot {name:s} adopted compute environment '
                            '{ce:s}'.format(name=self.name, ce=ce_name))

            jq_name = config.get(self._knot_name, 'job-queue')
            self._job_queue = aws.JobQueue(name=jq_name)
            mod_logger.info('Knot {name:s} adopted job queue {q:s}'.format(
                name=self.name, q=jq_name
            ))

            self._job_ids = config.get(self._knot_name, 'job_ids').split()
            self._jobs = [aws.BatchJob(job_id=jid) for jid in self.job_ids]
        else:
            job_definition_name = job_definition_name if job_definition_name \
                else name + '-cloudknot-job-definition'
            compute_environment_name = compute_environment_name \
                if compute_environment_name \
                else name + '-cloudknot-compute-environment'
            job_queue_name = job_queue_name if job_queue_name \
                else name + '-cloudknot-job-queue'

            # Validate and set the PARS
            if pars:
                if not isinstance(pars, Pars):
                    raise ValueError('pars must be a Pars instance.')
                self._pars = pars
                mod_logger.info('knot {name:s} adopted PARS {p:s}'.format(
                    name=self.name, p=self.pars.name
                ))
                pars_cleanup = False
            else:
                self._pars = Pars(name=self.name, policies=pars_policies)
                mod_logger.info('knot {name:s} created PARS {p:s}'.format(
                    name=self.name, p=self.pars.name
                ))
                pars_cleanup = True

            if docker_image:
                if any([func, image_script_path, image_work_dir]):
                    raise ValueError(
                        'you gave redundant, possibly conflicting input: '
                        '`docker_image` and one of [`func`, '
                        '`image_script_path`, `image_work_dir`]'
                    )

                if not isinstance(docker_image, dockerimage.DockerImage):
                    raise ValueError('docker_image must be a cloudknot '
                                     'DockerImage instance.')

                self._docker_image = docker_image
                mod_logger.info('Knot {name:s} adopted docker image {i:s}'
                                ''.format(name=self.name, i=docker_image.name))

            else:
                # Create and build the docker image
                self._docker_image = dockerimage.DockerImage(
                    func=func,
                    script_path=image_script_path,
                    dir_name=image_work_dir,
                    username=username
                )

            if not self.docker_image.images:
                self.docker_image.build(tags=image_tags)
                mod_logger.info(
                    'knot {name:s} built docker image {i!s}'
                    ''.format(name=self.name, i=self.docker_image.images)
                )

            if self.docker_image.repo_uri is None:
                # Create the remote repo
                repo_name = (repo_name if repo_name
                             else self.docker_image.images[0]['name'])

                # Later in __init__, we may abort this init because of
                # inconsistent job def, compute env, or job queue parameters
                # If we do that, we don't want to leave a bunch of newly
                # created resources around so keep track of whether this repo
                # was created or adopted.
                if config.has_option('docker-repos', repo_name):
                    # Pre-existing repo, no cleanup necessary
                    repo_cleanup = False
                else:
                    # Freshly created repo, cleanup necessary
                    repo_cleanup = True

                self._docker_repo = aws.DockerRepo(name=repo_name)

                mod_logger.info(
                    'knot {name:s} created/adopted docker repo '
                    '{r:s}'.format(name=self.name, r=self.docker_repo.name)
                )

                # Push to remote repo
                self.docker_image.push(repo=self.docker_repo)

                mod_logger.info(
                    "knot {name:s} pushed it's docker image to the repo "
                    "{r:s}".format(name=self.name, r=self.docker_repo.name)
                )
            else:
                repo_cleanup = False
                self._docker_repo = None

            try:
                # Create job definition
                self._job_definition = aws.JobDefinition(
                    name=job_definition_name,
                    job_role=self.pars.ecs_task_role,
                    docker_image=self.docker_image.repo_uri,
                    vcpus=job_def_vcpus,
                    memory=memory,
                    username=username,
                    retries=retries
                )

                mod_logger.info(
                    'knot {name:s} created job definition {jd:s}'.format(
                        name=self.name, jd=self.job_definition.name
                    )
                )

                # Later in __init__, we may abort this init because of
                # inconsistent compute env, or job queue parameters
                # If we do that, we don't want to leave a bunch of newly
                # created resources around so keep track of whether this job
                # def was created or adopted. Here, we created it, so cleanup
                # is needed
                jd_cleanup = True
            except aws.ResourceExistsException as e:
                # Job def already exists, retrieve it
                jd = aws.JobDefinition(arn=e.resource_id)

                # But confirm that all of the properties match the input
                # or that the input was unspecified (i.e. is None)
                eq_role = jd.job_role_arn == self.pars.ecs_task_role.arn
                eq_image = jd.docker_image == self.docker_image.repo_uri
                eq_vcpus = job_def_vcpus is None or jd.vcpus == job_def_vcpus
                eq_retries = retries is None or jd.retries == retries
                eq_mem = memory is None or jd.memory == memory
                eq_user = username is None or jd.username == username

                matches = {
                    'job role matches': eq_role,
                    'docker image matches': eq_image,
                    'VCPUs match': eq_vcpus,
                    'retries match': eq_retries,
                    'memory matches': eq_mem,
                    'username matches': eq_user
                }

                if not all(matches.values()):
                    if repo_cleanup:
                        self.docker_repo.clobber()

                    if pars_cleanup:
                        self.pars.clobber()

                    raise ValueError(
                        'The requested job definition already exists but '
                        'does not match the input parameters. '
                        '{matches!s}'.format(matches=matches)
                    )

                self._job_definition = jd
                # jd_cleanup description is same as above. Here, we adopted it,
                # so cleanup isn't needed
                jd_cleanup = False

                mod_logger.info(
                    'knot {name:s} adopted job definition {jd:s}'.format(
                        name=self.name, jd=self.job_definition.name
                    )
                )

            if self.job_definition.username != self.docker_image.username:
                raise ValueError("The username for this knot's job definition "
                                 "does not match the username for this knot's "
                                 "Docker image.")

            try:
                # Create compute environment
                self._compute_environment = aws.ComputeEnvironment(
                    name=compute_environment_name,
                    batch_service_role=self.pars.batch_service_role,
                    instance_role=self.pars.ecs_instance_role,
                    vpc=self.pars.vpc,
                    security_group=self.pars.security_group,
                    spot_fleet_role=self.pars.spot_fleet_role,
                    instance_types=instance_types,
                    resource_type=resource_type,
                    min_vcpus=min_vcpus,
                    max_vcpus=max_vcpus,
                    desired_vcpus=desired_vcpus,
                    image_id=image_id,
                    ec2_key_pair=ec2_key_pair,
                    tags=ce_tags,
                    bid_percentage=bid_percentage
                )

                mod_logger.info(
                    'knot {name:s} created compute environment {ce:s}'.format(
                        name=self.name, ce=self.compute_environment.name
                    )
                )

                # ce_cleanup logic same as for jd_cleanup
                ce_cleanup = True
            except aws.ResourceExistsException as e:
                # Compute environment already exists, retrieve it
                ce = aws.ComputeEnvironment(arn=e.resource_id)

                # But confirm that all of the properties match the input
                # or that the input was unspecified (i.e. is None)
                eq_bsr = (ce.batch_service_role_arn
                          == self.pars.batch_service_role.arn)
                eq_eir = (ce.instance_role_arn
                          == self.pars.ecs_instance_role.instance_profile_arn)
                eq_vpc = set(ce.subnets) == set(self.pars.vpc.subnet_ids)
                eq_sg = (ce.security_group_ids
                         == [self.pars.security_group.security_group_id])
                if resource_type == 'SPOT':
                    eq_sfr = (ce.spot_fleet_role_arn
                              == self.pars.spot_fleet_role.arn)
                else:
                    eq_sfr = ce.spot_fleet_role_arn is None
                eq_it = (instance_types is None
                         or ce.instance_types == instance_types)
                eq_rt = (resource_type is None
                         or ce.resource_type == resource_type)
                eq_min_vcpus = min_vcpus is None or ce.min_vcpus == min_vcpus
                eq_max_vcpus = max_vcpus is None or ce.max_vcpus == max_vcpus
                eq_des_vcpus = (desired_vcpus is None
                                or ce.desired_vcpus == desired_vcpus)
                eq_image_id = image_id is None or ce.image_id == image_id
                eq_kp = ec2_key_pair is None or ce.ec2_key_pair == ec2_key_pair
                eq_tags = ce_tags is None or ce.tags == ce_tags
                eq_bp = (bid_percentage is None
                         or ce.bid_percentage == bid_percentage)

                matches = {
                    'batch service role matches': eq_bsr,
                    'instance profile matches': eq_eir,
                    'subnets match': eq_vpc,
                    'security groups match': eq_sg,
                    'spot fleet role matches': eq_sfr,
                    'instance types match': eq_it,
                    'resource type matches': eq_rt,
                    'min VCPUs match': eq_min_vcpus,
                    'max VCPUs match': eq_max_vcpus,
                    'desired VCPUs match': eq_des_vcpus,
                    'image ID matches': eq_image_id,
                    'EC2 key pair matches': eq_kp,
                    'tags match': eq_tags,
                    'bid percentage matches': eq_bp
                }

                if not all(matches.values()):
                    if repo_cleanup:
                        self.docker_repo.clobber()

                    if jd_cleanup:
                        self.job_definition.clobber()

                    if pars_cleanup:
                        self.pars.clobber()

                    raise ValueError(
                        'The requested compute environment already exists '
                        'but does not match the input parameters. '
                        '{matches!s}.'.format(matches=matches)
                    )

                self._compute_environment = ce
                # ce_cleanup logic same as for jd_cleanup
                ce_cleanup = False
                mod_logger.info(
                    'knot {name:s} adopted compute environment {ce:s}'.format(
                        name=self.name, ce=self.compute_environment.name
                    )
                )

            try:
                # Create job queue
                self._job_queue = aws.JobQueue(
                    name=job_queue_name,
                    compute_environments=self.compute_environment,
                    priority=priority
                )

                mod_logger.info(
                    'knot {name:s} created job queue '
                    '{jq:s}'.format(name=self.name, jq=self.job_queue.name)
                )
            except aws.ResourceExistsException as e:
                # Job queue already exists, retrieve it
                jq = aws.JobQueue(arn=e.resource_id)

                # But confirm that all of the properties match the input
                # or that the input was unspecified (i.e. is None)
                ce_arns = [d['computeEnvironment']
                           for d in jq.compute_environment_arns]
                eq_ce = ce_arns == [self.compute_environment.arn]
                eq_priority = priority is None or jq.priority == priority

                matches = {
                    'compute environment ARNS match': eq_ce,
                    'priority matches': eq_priority
                }

                if not all(matches.values()):
                    if repo_cleanup:
                        self.docker_repo.clobber()

                    if jd_cleanup:
                        self.job_definition.clobber()

                    if ce_cleanup:
                        self.compute_environment.clobber()

                    if pars_cleanup:
                        self.pars.clobber()

                    raise ValueError(
                        'The requested job queue already exists '
                        'but does not match the input parameters. '
                        '{matches!s}'.format(matches=matches)
                    )

                self._job_queue = jq
                mod_logger.info(
                    'knot {name:s} adopted job queue '
                    '{jq:s}'.format(name=self.name, jq=self.job_queue.name)
                )

            self._jobs = []
            self._job_ids = []

            # Save the new Knot resources in config object
            # Use config.set() for python 2.7 compatibility
            config = configparser.ConfigParser()
            config.read(get_config_file())
            config.add_section(self._knot_name)
            config.set(self._knot_name, 'region', self.region)
            config.set(self._knot_name, 'profile', self.profile)
            config.set(self._knot_name, 'pars', self.pars.name)
            config.set(self._knot_name, 'docker-image', self.docker_image.name)
            config.set(self._knot_name, 'docker-repo',
                       self.docker_repo.name if self.docker_repo else 'None')
            config.set(self._knot_name, 'job-definition',
                       self.job_definition.name)
            config.set(self._knot_name, 'compute-environment',
                       self.compute_environment.name)
            config.set(self._knot_name, 'job-queue', self.job_queue.name)
            config.set(self._knot_name, 'job_ids', '')

            # Save config to file
            with open(get_config_file(), 'w') as f:
                config.write(f)

    # Declare read-only properties
    @property
    def knot_name(self):
        """The section name for this knot in the cloudknot config file"""
        return self._knot_name

    @property
    def pars(self):
        """The Pars instance attached to this knot"""
        return self._pars

    @property
    def docker_image(self):
        """The DockerImage instance attached to this knot"""
        return self._docker_image

    @property
    def docker_repo(self):
        """The DockerRepo instance attached to this knot"""
        return self._docker_repo

    @property
    def job_definition(self):
        """The JobDefinition instance attached to this knot"""
        return self._job_definition

    @property
    def job_queue(self):
        """The JobQueue instance attached to this knot"""
        return self._job_queue

    @property
    def compute_environment(self):
        """The ComputeEnvironment instance attached to this knot"""
        return self._compute_environment

    @property
    def jobs(self):
        """List of BatchJob instances that this knot has launched"""
        return self._jobs

    @property
    def job_ids(self):
        """List of batch job IDs that this knot has launched"""
        return self._job_ids

    def submit(self, commands=None, env_vars=None):
        """Submit batch jobs for a range of commands and environment vars

        Parameters
        ----------
        commands : sequence of sequence of strings
            Sequence of commands. This method will submit one batch job for
            each command in the sequence. Each individual command must be a
            sequence of strings since the command eventaully becomes arguments
            to the `docker run` command. For example, if you wanted to pass
            the commands `echo 1`, `echo 2`, `echo 3`, then then you would use
            `submit(commands=[["echo", "1"], ["echo", "2"], ["echo", "3"]])`

        env_vars : sequence of sequence of strings
            Sequence of environment variables. This method will submit one
            batch job for each environment variable set in the sequence
        """
        if self.clobbered:
            raise aws.ResourceClobberedException(
                'This Knot has already been clobbered.',
                self.name
            )

        self.check_profile_and_region()

        # User must supply either commands or env_vars
        if not (commands or env_vars):
            raise ValueError('You must supply either commands or env_vars.')

        # commands should be a sequence of sequences of strings
        if commands and not all(all(isinstance(s, six.string_types)
                                    for s in sublist)
                                for sublist in commands):
            raise ValueError('commands must be a sequence of '
                             'sequences of strings')

        # env_vars should be a sequence of sequences of dicts
        if env_vars and not all(all(isinstance(s, dict) for s in sublist)
                                for sublist in env_vars):
            raise ValueError('env_vars must be a sequence of '
                             'sequences of dicts')

        # and each dict should have only 'name' and 'value' keys
        if env_vars and not all(all(set(d.keys()) == {'name', 'value'}
                                    for d in sublist)
                                for sublist in env_vars):
            raise ValueError('each dict in env_vars must have keys "name" '
                             'and "value"')

        if commands and env_vars and len(commands) != len(env_vars):
            raise ValueError('commands and env_vars must be the same length')

        if not commands:
            commands = [None] * len(env_vars)
        elif not env_vars:
            env_vars = [None] * len(commands)

        for command, env in zip(commands, env_vars):
            job = aws.BatchJob(
                name='{n:s}-{i:d}'.format(n=self.name, i=len(self.job_ids)),
                job_queue=self.job_queue,
                job_definition=self.job_definition,
                commands=command,
                environment_variables=env
            )

            self._jobs.append(job)
            self._job_ids.append(job.job_id)

        config = configparser.ConfigParser()
        config.read(get_config_file())
        config.set(self._knot_name, 'job_ids', ' '.join(self.job_ids))
        # Save config to file
        with open(get_config_file(), 'w') as f:
            config.write(f)

    def get_jobs(self):
        """Return a list of dictionaries containing job instances and info

        Returns
        -------
        jobs_info: list
            A list of dicts [{'job': BatchJob instance, 'name': BatchJob.name,
            'status': BatchJob.status, 'id': BatchJob.job_id},]
        """
        if self.clobbered:
            raise aws.ResourceClobberedException(
                'This Knot has already been clobbered.',
                self.name
            )

        self.check_profile_and_region()

        jobs_info = [
            {
                'job': job,
                'name': job.name,
                'status': job.status['status'],
                'attempts': job.status['attempts'],
                'status-reason': job.status['statusReason'],
                'id': job.job_id
            }
            for job in self.jobs
        ]

        return jobs_info

    def view_jobs(self):
        """Print the job_id, name, and status of all jobs in self.jobs"""
        if self.clobbered:
            raise aws.ResourceClobberedException(
                'This Knot has already been clobbered.',
                self.name
            )

        self.check_profile_and_region()

        order = {'SUBMITTED': 0, 'PENDING': 1, 'RUNNABLE': 2, 'STARTING': 3,
                 'RUNNING': 4, 'FAILED': 5, 'SUCCEEDED': 6}
        job_info = sorted(self.get_jobs(), key=lambda j: order[j['status']])

        fmt = '{id:12s}        {name:20s}        {status:9s}'
        header = fmt.format(id='Job ID', name='Name', status='Status')
        print(header)
        print('-' * len(header))

        for job in job_info:
            print(fmt.format(**job))

    def clobber(self, clobber_pars=False, clobber_repo=False,
                clobber_image=False):
        """Delete associated AWS resources and remove section from config

        Parameters
        ----------
        clobber_pars : boolean
            If true, clobber the associated Pars instance
            Default: False

        clobber_repo : boolean
            If true, clobber the associated DockerRepo instance
            Default: False

        clobber_image : boolean
            If true, clobber the associated DockerImage instance
            Default: False
        """
        if self.clobbered:
            return

        self.check_profile_and_region()

        # Delete all associated AWS resources
        # Iterate over copy of self.jobs since we are removing from
        # the list while iterating
        for job in list(self.jobs):
            job.clobber()
            self._jobs.remove(job)

        self.job_queue.clobber()
        self.compute_environment.clobber()
        self.job_definition.clobber()

        if clobber_repo and self.docker_repo:
            self.docker_repo.clobber()

        if clobber_image:
            self.docker_image.clobber()

        if clobber_pars:
            self.pars.clobber()
            mod_logger.info('Knot {name:s} clobbered PARS {pars:s}'.format(
                name=self.name, pars=self.pars.name
            ))

        # Remove this section from the config file
        config = configparser.ConfigParser()
        config.read(get_config_file())
        config.remove_section(self._knot_name)
        with open(get_config_file(), 'w') as f:
            config.write(f)

        # Set the clobbered parameter to True,
        # preventing subsequent method calls
        self._clobbered = True

        mod_logger.info('Clobbered Knot {name:s}'.format(name=self.name))
