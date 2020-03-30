import click
import boto3


def validate_subnets(ctx, param, value):
    subnets = value.split(",")
    if len(subnets) <= 1:
        raise click.BadParameter(
            "subnet_ids should be a comma separated list of subnets")
    return subnets


@click.command()
@click.option('--vpc_id', required=True, help="List of vpcs")
@click.option('--no_npip/--npip', default=True, help="Use --npip for NPIP deployment")
@click.option('--subnet_ids', required=True, callback=validate_subnets, help="Comma separated list of subnets")
@click.version_option()
def cli(vpc_id, subnet_ids, no_npip):
    """Validates the configuration of VPC."""
    check_dns(vpc_id)
    check_nw(vpc_id, subnet_ids, no_npip)


# Checks dns realted settings
def check_dns(vpc_id):
    client = boto3.client('ec2')
    try:
        dns_support = client.describe_vpc_attribute(
            Attribute='enableDnsSupport', VpcId=vpc_id)
    except Exception as e:
        raise click.BadParameter(
            "The vpc ID '{}' does not exist".format(vpc_id))

    if dns_support['EnableDnsSupport']['Value'] == True:
        click.secho('☑ DNS resolution enabled', fg='green')
    else:
        click.secho('☒ DNS resolution not enabled',  fg='red')

    dns_host = client.describe_vpc_attribute(
        Attribute='enableDnsHostnames', VpcId=vpc_id)
    if dns_host['EnableDnsHostnames']['Value'] == True:
        click.secho('☑ Dns hostnames enabled', fg='green')
    else:
        click.secho('☒ Dns hostnames not enabled',  fg='red')


# Checks networking
def check_nw(vpc_id, subnet_ids, no_npip):
    check_nw_common(vpc_id, subnet_ids)
    if no_npip == True:
        check_no_npip(vpc_id, subnet_ids)
    else:
        check_npip(vpc_id, subnet_ids)


# Common checks
# 1 . Checks whether IGW is attached to the VPC
# 2 . Checks whether each subnet has a different Availability Zone
# 3 . Checks whether netmask is between /17 and /25
def check_nw_common(vpc_id, subnet_ids):
    client = boto3.client('ec2')
    ec2 = boto3.resource('ec2')

    azs = []
    for subnet_id in subnet_ids:
        subnet = ec2.Subnet(subnet_id)

        if subnet.vpc_id != vpc_id:
            click.secho("☒ Subnet with id: {} belongs to a different VPC".format(
                subnet_id),  fg='red')

        if subnet.availability_zone in azs:
            click.secho(
                "☒ More than one subnet per availability zone is not allowed",  fg='red')
        else:
            azs.append(subnet.availability_zone)

        if (int(subnet.cidr_block.split("/")[1]) > 26) | (int(subnet.cidr_block.split("/")[1]) < 17):
            click.secho(
                "☒ Subnet netmask is not between /17 and /26 : {}".format(subnet_id),  fg='red')


# Checks NPIP requirements
#1.) Checks if a Nat gateway is atttached
#2.) Checks if there is a '0.0.0.0/0' route to a gateway/applicance for all route tables
def check_npip(vpc_id, subnet_ids):
    client = boto3.client('ec2')
    ec2 = boto3.resource('ec2')
    nat_gws = client.describe_nat_gateways(
        Filters=[
            {
                'Name': 'vpc-id',
                'Values': [vpc_id],
            },
        ],
    )

    if (len(nat_gws['NatGateways']) == 0):
        click.secho(
            "☒ No NAT gateway atttached to the VPC. Custom appliance?",  fg='red')

    route_tables = get_route_tables(vpc_id, subnet_ids)
    for route_table in route_tables:
        route_to_nat = False
        for ra in route_table.routes_attribute:
            if ra.get('DestinationCidrBlock') == '0.0.0.0/0' and ra.get('GatewayId') is None:
                route_to_nat = True
        if route_to_nat == False:
            click.secho("☒ 0.0.0.0/0 Route to custom appliance / Nat gateway not found for route table:{}".format(route_table.id),  fg='red')


# Check NW for No NPIP speciific requirements
# 1.) Check if Internet Gateway is attatched
# 2.) Check if 0.0.0.0/0 Route to Internet Gateway exists for all route tables
def check_no_npip(vpc_id, subnet_ids):
    client = boto3.client('ec2')
    igws = client.describe_internet_gateways(
        Filters=[
            {
                'Name': 'attachment.vpc-id',
                'Values': [
                    vpc_id,
                ],
            },
        ],
    )
    if len(igws['InternetGateways']) < 0:
        click.secho("☒ No Internet Gateway atttached to the VPC",  fg='red')

    route_tables = get_route_tables(vpc_id, subnet_ids)

    for route_table in route_tables:
        route_to_igw = False
        for ra in route_table.routes_attribute:
            if ra.get('DestinationCidrBlock') == '0.0.0.0/0' and ra.get('GatewayId') is not None:
                route_to_igw = True
        if route_to_igw == False:
            click.secho("☒ 0.0.0.0/0 Route to Internet gateway not found for route table:{}".format(route_table),  fg='red')

    


# Gets the list of route tables associated to the subnet
def get_route_tables(vpc_id, subnet_ids):
    ec2 = boto3.resource('ec2')
    # main route table
    route_tables_itr = ec2.route_tables.filter(
        Filters=[
            {
                'Name': 'vpc-id',
                'Values': [vpc_id]
            },
        ])

    for route_table_info in route_tables_itr:
        for association in route_table_info.associations:
            if association.main == True:
                main_route_table = route_table_info

    route_tables = {}

    # Find route tables associated with subnet
    for subnet_id in subnet_ids:
        route_tables_itr = ec2.route_tables.filter(
            Filters=[
                {
                    'Name': 'association.subnet-id',
                    'Values': [subnet_id]
                },
            ])

        for route_table_info in route_tables_itr:
            route_tables[subnet_id] = route_table_info
        # If not route table is present, use the default route table
        if subnet_id not in route_tables:
            route_tables[subnet_id] = main_route_table

    return set(route_tables.values())
