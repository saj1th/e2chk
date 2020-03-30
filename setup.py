from setuptools import setup

setup(
    name="e2chk",
    version="1.0",
    py_modules=["e2chk"],
    include_package_data=True,
    install_requires=["click", "boto3"],
    entry_points="""
        [console_scripts]
        e2chk=e2chk:cli
    """,
)
