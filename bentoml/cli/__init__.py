# Copyright 2019 Atalaya Tech, Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

# http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import json
import click

from bentoml.archive import load
from bentoml.server import BentoAPIServer
from bentoml.server.gunicorn_server import GunicornApplication, get_gunicorn_worker_count
from bentoml.cli.click_utils import DefaultCommandGroup, conditional_argument
from bentoml.deployment.serverless import ServerlessDeployment
from bentoml.deployment.sagemaker import SagemakerDeployment
from bentoml.utils.exceptions import BentoMLException

SERVERLESS_PLATFORMS = ['aws-lambda', 'aws-lambda-py2', 'gcp-function']

CLICK_COLOR_SUCCESS = 'greeen'
CLICK_COLOR_ERROR = 'red'


def _echo(message, color=CLICK_COLOR_SUCCESS):
    click.echo('BentoML: ', nl=False)
    click.secho(message, fg=color)


def create_bentoml_cli(installed_archive_path=None):
    # pylint: disable=unused-variable

    @click.group(cls=DefaultCommandGroup)
    @click.version_option()
    def bentoml_cli():
        """
        BentoML CLI tool
        """

    # Example Usage: bentoml API_NAME /SAVED_ARCHIVE_PATH --input=INPUT
    @bentoml_cli.command(default_command=True,
                         default_command_usage="API_NAME BENTO_ARCHIVE_PATH --input=INPUT",
                         default_command_display_name="<API_NAME>",
                         help="Run a API defined in saved BentoArchive with cli args as input",
                         context_settings=dict(
                             ignore_unknown_options=True,
                             allow_extra_args=True,
                         ))
    @click.argument('api-name', type=click.STRING)
    @conditional_argument(installed_archive_path is None, 'archive-path', type=click.STRING)
    @click.pass_context
    def run(ctx, api_name, archive_path=installed_archive_path):
        """
        Run an API definied in the BentoService loaded from archive
        """
        model_service = load(archive_path)

        try:
            api = next((api for api in model_service.get_service_apis() if api.name == api_name))
        except StopIteration:
            raise ValueError("Can't find API '{}' in Service '{}'".format(
                api_name, model_service.name))

        api.handle_cli(ctx.args)

    # Example Usage: bentoml info /SAVED_ARCHIVE_PATH
    @bentoml_cli.command()
    @conditional_argument(installed_archive_path is None, 'archive-path', type=click.STRING)
    def info(archive_path=installed_archive_path):
        """
        List all APIs definied in the BentoService loaded from archive
        """
        model_service = load(archive_path)
        service_apis = model_service.get_service_apis()
        output = json.dumps(
            dict(name=model_service.name, version=model_service.version,
                 apis=[api.name for api in service_apis]), indent=2)
        print(output)

    # Example Usage: bentoml serve ./SAVED_ARCHIVE_PATH --port=PORT
    @bentoml_cli.command()
    @conditional_argument(installed_archive_path is None, 'archive-path', type=click.STRING)
    @click.option('--port', type=click.INT, default=BentoAPIServer._DEFAULT_PORT)
    def serve(port, archive_path=installed_archive_path):
        """
        Start REST API server hosting BentoService loaded from archive
        """
        model_service = load(archive_path)
        server = BentoAPIServer(model_service, port=port)
        server.start()

    # Example Usage: bentoml serve-gunicorn ./SAVED_ARCHIVE_PATH --port=PORT --workers=WORKERS
    @bentoml_cli.command()
    @conditional_argument(installed_archive_path is None, 'archive-path', type=click.STRING)
    @click.option('-p', '--port', type=click.INT, default=BentoAPIServer._DEFAULT_PORT)
    @click.option('-w', '--workers', type=click.INT, default=get_gunicorn_worker_count())
    def serve_gunicorn(port, workers, archive_path=installed_archive_path):
        """
        Start REST API gunicorn server hosting BentoService loaded from archive
        """
        model_service = load(archive_path)
        server = BentoAPIServer(model_service, port=port)
        gunicorn_app = GunicornApplication(server.app, port, workers)
        gunicorn_app.run()

    # pylint: enable=unused-variable
    return bentoml_cli


def cli():
    _cli = create_bentoml_cli()

    # Commands created here aren't mean to be used from generated service archive.  They
    # are used as part of BentoML cli commands only.

    # pylint: disable=unused-variable

    # Example usage: bentoml deploy /ARCHIVE_PATH --platform=aws-lambda
    @_cli.command(help='Deploy BentoML archive as REST endpoint')
    @click.argument('archive-path', type=click.STRING)
    @click.option('--platform', type=click.Choice([
        'aws-lambda', 'aws-lambda-py2', 'gcp-function', 'aws-sagemaker', 'azure-ml', 'algorithmia'
    ]), required=True)
    @click.option('--region', type=click.STRING)
    @click.option('--stage', type=click.STRING)
    @click.option('--api-name', type=click.STRING)
    @click.option('--instance-type', type=click.STRING)
    @click.option('--instance-count', type=click.INT)
    def deploy(archive_path, platform, region, stage, api_name, instance_type, instance_count):
        if platform in SERVERLESS_PLATFORMS:
            deployment = ServerlessDeployment(archive_path, platform, region, stage)
        elif platform == 'aws-sagemaker':
            deployment = SagemakerDeployment(archive_path, api_name, region, instance_count,
                                             instance_type)
        else:
            raise BentoMLException('Deploying with "--platform=%s" is not supported ' % platform +
                                   'in the current version of BentoML')
        output_path = deployment.deploy()

        _echo('Deploy to {platform} complete!'.format(platform=platform))
        _echo(
            'Deployment archive is saved at {output_path}'.format(output_path=output_path))
        return

    # Example usage: bentoml delete-deployment ARCHIVE_PATH --platform=aws-lambda
    @_cli.command(help='Delete active BentoML deployment')
    @click.argument('archive-path', type=click.STRING)
    @click.option('--platform', type=click.Choice([
        'aws-lambda', 'aws-lambda-py2', 'gcp-function', 'aws-sagemaker', 'azure-ml', 'algorithmia'
    ]), required=True)
    @click.option('--region', type=click.STRING, required=True)
    @click.option('--api-name', type=click.STRING)
    @click.option('--stage', type=click.STRING)
    def delete_deployment(archive_path, platform, region, stage, api_name):
        if platform in SERVERLESS_PLATFORMS:
            deployment = ServerlessDeployment(archive_path, platform, region, stage)
        elif platform == 'aws-sagemaker':
            deployment = SagemakerDeployment(archive_path, api_name, region)
        else:
            raise BentoMLException('Remove deployment with --platform=%s' % platform +
                                   'is not supported in the current version of BentoML')
        result = deployment.delete()
        if result:
            _echo(
                'Delete {platform} deployment successful'.format(platform=platform))
        else:
            _echo(
                'Delete {platform} deployment unsuccessful'.format(platform=platform),
                CLICK_COLOR_ERROR)
        return

    # Example usage: bentoml check-deployment-status ARCHIVE_PATH --platform=aws-lambda
    @_cli.command(help='Check deployment status of BentoML archive')
    @click.argument('archive-path', type=click.STRING)
    @click.option('--platform', type=click.Choice([
        'aws-lambda', 'aws-lambda-py2', 'gcp-function', 'aws-sagemaker', 'azure-ml', 'algorithmia'
    ]), required=True)
    @click.option('--region', type=click.STRING, required=True)
    @click.option('--stage', type=click.STRING)
    @click.option('--api-name', type=click.STRING)
    def check_deployment_status(archive_path, platform, region, stage, api_name):
        if platform in SERVERLESS_PLATFORMS:
            deployment = ServerlessDeployment(archive_path, platform, region, stage)
        elif platform == 'aws-sagemaker':
            deployment = SagemakerDeployment(archive_path, api_name, region)
        else:
            raise BentoMLException('check deployment status with --platform=%s' % platform +
                                   'is not supported in the current version of BentoML')

        deployment.check_status()
        return

    # pylint: enable=unused-variable
    _cli()


if __name__ == '__main__':
    cli()
