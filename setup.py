from setuptools import find_packages, setup
import os


# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='django_iiif',
    version='0.11',
    packages=find_packages(),
    include_package_data=True,
    license='BSD License',  # example license
    description='Simple Django-IIIF integration.',
    long_description='django-iiif is a package designed to make integrating the IIIF Image API easier by extending Django\'s ImageField',
    url='https://github.com/rogerhoward/django-iiif/',
    author='Roger Howard',
    author_email='rogerhoward+django@gmail.com',
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Framework :: Django :: 1.11',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)