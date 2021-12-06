# -*- coding: utf-8 -*-
"""
install
"""
from distutils.core import setup

name='filedownloader'

setup(name=name,
      version='1.0.0',
      packages=[name,],
      package_dir={name: 'src'},
      description='Python library for file download',
      license='Apache-2.0 License',
      author='anexplore',
      url='https://github.com/anexplore/filedownloader.git',
      install_requires=[
        'requests'
      ],
      python_requires='>=3.0, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*',
      classifiers=['Development Status :: 1-Release',
                    'Intended Audience :: Developers',
                    'License :: Apache-2.0 License',
                    'Programming Language :: Python :: 3+',
                    'Topic :: Utilities']
      )
