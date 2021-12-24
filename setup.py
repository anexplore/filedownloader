# -*- coding: utf-8 -*-
"""
install
"""
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

with open('README.md', encoding='utf8') as f:
    readme = f.read()

name='file_mt_downloader'

setup(name=name,
      version='1.0.0',
      packages=[name,],
      package_dir={name: 'src'},
      description='Python library for file download',
      long_description=readme,
      long_description_content_type="text/markdown",
      license='Apache-2.0 License',
      author='anexplore',
      maintainer='anexplore',
      url='https://github.com/anexplore/filedownloader.git',
      keywords=[
        'file download',
        'downloader'
      ],
      install_requires=[
        'requests'
      ],
      python_requires='>=3.0, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*',
      classifiers=[
          'Programming Language :: Python :: 3',
          'License :: OSI Approved :: Apache Software License',
          'Operating System :: OS Independent'
     ]
    )
