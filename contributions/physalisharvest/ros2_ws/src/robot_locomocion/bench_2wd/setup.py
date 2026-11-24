from setuptools import setup


setup(
    name='bench_2wd',
    version='0.1.0',
    packages=['bench_2wd'],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/bench_2wd']),
        ('share/bench_2wd', ['package.xml']),
    ],
    description='Banco ROS 2 de coordenadas sin actuadores.',
    maintainer='PhysalisHarvest',
    maintainer_email='maintainers@example.org',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'receiver = bench_2wd.receiver:main',
            'smoke_test = bench_2wd.smoke_test:main',
        ],
    },
)
