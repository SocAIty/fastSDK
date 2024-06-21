from setuptools import setup, find_packages

setup(
    name='fastsdk',
    version='0.0.1',
    description="Connect to and convert any web endpoint into an python SDK. Built-in threading, async jobs and fastapi/runpod/socaity endpoint support.",
    author='SocAIty',
    packages=find_packages(),
    install_requires=[
        'req',
        'tqdm',
        'soundfile'
    ]
)