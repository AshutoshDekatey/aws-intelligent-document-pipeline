"""Create browser-uploadable artifacts from a local SAM build."""
import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

ROOT = Path(__file__).resolve().parents[1]


class CloudFormationLoader(yaml.SafeLoader):
    pass


def intrinsic(loader, name, node):
    if isinstance(node, SequenceNode):
        value = loader.construct_sequence(node)
    elif isinstance(node, MappingNode):
        value = loader.construct_mapping(node)
    elif isinstance(node, ScalarNode):
        value = loader.construct_scalar(node)
    else:
        raise TypeError(node)
    if name == 'GetAtt' and isinstance(value, str):
        value = value.split('.', 1)
    return {name if name == 'Ref' else f'Fn::{name}': value}


CloudFormationLoader.add_multi_constructor('!', intrinsic)


def console_template():
    template = yaml.load((ROOT / 'template.yaml').read_text(), Loader=CloudFormationLoader)
    template['Parameters']['CodeBucket'] = {'Type': 'String', 'Description': 'Private same-region artifact bucket'}
    template['Parameters']['CodeKey'] = {'Type': 'String', 'Default': 'finance-lambda.zip',
                                         'Description': 'Exact key of the uploaded Lambda ZIP'}
    function = template['Resources']['Processor']['Properties']
    function['CodeUri'] = {'Bucket': {'Ref': 'CodeBucket'}, 'Key': {'Ref': 'CodeKey'}}
    pipeline = template['Resources']['Pipeline']['Properties']
    pipeline['Definition'] = json.loads((ROOT / pipeline.pop('DefinitionUri')).read_text())
    return template


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, default=ROOT / '.aws-sam/build/Processor')
    parser.add_argument('--out', type=Path, default=ROOT / 'artifacts/console')
    args = parser.parse_args()
    core = args.build / 'pydantic_core'
    linux_extensions = list(core.glob('*manylinux*x86_64*.so')) + list(core.glob('*x86_64-linux-gnu.so'))
    if not (args.build / 'workflow.py').is_file() or not linux_extensions:
        parser.error('Run sam build on Linux x86_64 with Python 3.12, or use sam build --use-container')
    args.out.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.out / 'finance-lambda.zip', 'w', ZIP_DEFLATED) as archive:
        for file in sorted(args.build.rglob('*')):
            if file.is_file() and '__pycache__' not in file.parts and file.suffix != '.pyc':
                archive.write(file, file.relative_to(args.build).as_posix())
    target = args.out / 'finance-console.json'
    target.write_text(json.dumps(console_template(), indent=2) + '\n')
    if target.stat().st_size > 51_200:
        raise SystemExit('CloudFormation direct upload template size exceeds 51,200 bytes')
    print(f'Console bundle written to {args.out}')


if __name__ == '__main__':
    main()
