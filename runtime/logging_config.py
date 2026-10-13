"""Derive credential-redacting file logging from the official application (MIT)."""
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
from common import CONFIG

def configure(application):
    with zipfile.ZipFile(Path(application) / 'lib/ace.jar') as archive:
        config = ET.fromstring(archive.read('logback.xml'))
    expression = r'(mongodb(?:\+srv)?://[^:\s/@]+:)[^@\s]+@'
    for variable in config.findall('variable'):
        if variable.get('name') == 'logPattern':
            pattern = variable.get('value').replace('%message', "%replace(%message){'" + expression + "','$1[REDACTED]@'}")
            variable.set('value', pattern + "%replace(%ex){'" + expression + "','$1[REDACTED]@'}%nopex")
    for appender in list(config.findall('appender')):
        if appender.get('name') == 'AnalyticsAppender':
            config.remove(appender)
    for parent in config.iter():
        for child in list(parent):
            if child.tag == 'appender-ref' and child.get('ref') == 'AnalyticsAppender':
                parent.remove(child)
    ET.indent(config)
    ET.ElementTree(config).write(CONFIG / 'logback.xml', encoding='utf-8', xml_declaration=True)
    (CONFIG / 'logback.xml').chmod(0o644)
