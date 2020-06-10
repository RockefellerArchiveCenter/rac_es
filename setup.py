from setuptools import find_packages, setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='rac_es',
    version='0.4.4',
    description="Helpers for Rockefeller Archive Center's Elasticsearch implementation.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='http://github.com/RockefellerArchiveCenter/rac_es',
    author='Rockefeller Archive Center',
    author_email='archive@rockarch.org',
    license='MIT',
    packages=find_packages(),
    install_requires=[
        'datetime',
        'elasticsearch_dsl',
        'shortuuid',
    ],
    test_suite='nose.collector',
    tests_require=['nose'],
    zip_safe=False)
