"""Scoped database privileges required by UniFi's external-MongoDB restore path."""
import json
from common import CONFIG

DATABASES = ['unifi', 'unifi_stat', 'unifi_audit']
RESTORE_DATABASES = [name + '_restore' for name in DATABASES]
FSYNC_ROLE = 'unifi-riscv-fsync'

def required_roles():
    return ([{'role': 'dbOwner', 'db': name} for name in DATABASES + RESTORE_DATABASES + ['local']]
            + [{'role': 'clusterMonitor', 'db': 'admin'}])

def ensure_restore_permissions():
    """Add only missing restore DB roles; preserve credentials and custom grants."""
    from pymongo import MongoClient
    credentials = json.loads((CONFIG / 'mongo-credentials.json').read_text())
    with MongoClient('127.0.0.1', 27017, username=credentials['admin_user'],
                     password=credentials['admin_password'], authSource='admin', serverSelectionTimeoutMS=5000) as client:
        users = client.admin.command('usersInfo', credentials['user'])['users']
        if len(users) != 1:
            raise RuntimeError('Existing application database user was not found')
        existing = {(r['role'], r['db']) for r in users[0]['roles']}
        missing = [{'role': 'dbOwner', 'db': name} for name in RESTORE_DATABASES if ('dbOwner', name) not in existing]
        privileges = [{'resource': {'cluster': True}, 'actions': ['fsync']}]
        found = client.admin.command('rolesInfo', {'role': FSYNC_ROLE, 'db': 'admin'}, showPrivileges=True)['roles']
        if not found:
            client.admin.command('createRole', FSYNC_ROLE, privileges=privileges, roles=[])
        elif found[0]['privileges'] != privileges or found[0]['roles']:
            raise RuntimeError('Reserved migration-fsync role differs; refusing to overwrite it')
        if (FSYNC_ROLE, 'admin') not in existing:
            missing.append({'role': FSYNC_ROLE, 'db': 'admin'})
        if missing:
            client.admin.command('grantRolesToUser', credentials['user'], roles=missing)
        return [role['db'] if role['role'] == 'dbOwner' else 'cluster:fsync' for role in missing]
