from setuptools import setup


setup(
    name="bench_2wd_drv8833",
    version="0.1.0",
    packages=["bench_2wd_drv8833"],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/bench_2wd_drv8833"]),
        ("share/bench_2wd_drv8833", ["package.xml"]),
    ],
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "controller = bench_2wd_drv8833.controller:main",
            "aruco_source = bench_2wd_drv8833.aruco_source:main",
            "session = bench_2wd_drv8833.session:main",
            "monitor = bench_2wd_drv8833.monitor:main",
        ]
    },
)
