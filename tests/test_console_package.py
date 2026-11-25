import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_browser_template_preserves_asl_and_targets_packaged_lambda():
    spec = importlib.util.spec_from_file_location('package_console', ROOT / 'scripts/package_console.py')
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    template = package.console_template()
    resources = template['Resources']
    props = resources['Pipeline']['Properties']
    assert props['Definition'] == json.loads((ROOT / 'statemachine/pipeline.asl.json').read_text())
    assert 'DefinitionUri' not in props
    assert resources['Processor']['Properties']['CodeUri'] == {
        'Bucket': {'Ref': 'CodeBucket'}, 'Key': {'Ref': 'CodeKey'}}
    assert props['Definition']['States']['IgnoreFolderMarkers']['Choices'][0]['Next'] == 'FolderMarker'
    assert props['Definition']['States']['IgnoreFolderMarkers']['Default'] == 'ValidateDocument'
    assert resources['DeliveryDeadLetterQueue']['Properties']['SqsManagedSseEnabled'] is True
