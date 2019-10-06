from setuptools import setup

setup(name='rac_es',
      version='0.1',
      description="Helpers for Rockefeller Archive Center's Elasticsearch implementation.",
      url='http://github.com/RockefellerArchiveCenter/rac_es',
      author='Rockefeller Archive Center',
      author_email='archive@rockarch.org',
      license='MIT',
      packages=['rac_es'],
      install_requires=[
        'datetime',
        'elasticsearch_dsl',
        'shortuuid',
      ],
      test_suite='nose.collector',
      tests_require=['nose'],
      zip_safe=False)
