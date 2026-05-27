from setuptools import find_packages, setup
import os

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='djiiif',
    version='0.23',

    packages=find_packages(exclude=["tests", "tests.*"]),
    install_requires=['Django'],
    include_package_data=True,
    license='BSD License',  # example license
    description='Simple IIIF integration for Django.',
    long_description='djiiif is a package designed to make integrating the IIIF Image API easier by extending Django\'s ImageField',
    url='https://github.com/rogerhoward/djiiif/',
    author='Roger Howard',
    author_email='rogerhoward+django@gmail.com',
    python_requires='>=3.10',
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)