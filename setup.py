#!/usr/bin/env python3
"""
Setup script for Twin - Voice-Controlled Home Assistant
"""

from setuptools import setup, find_packages
import os

# Read the README file
def read_readme():
    with open(os.path.join(os.path.dirname(__file__), 'docs', 'README.md'), 'r', encoding='utf-8') as f:
        return f.read()

# Read requirements
def read_requirements():
    with open('requirements.txt', 'r') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name="twin-assistant",
    version="1.0.0",
    description="Voice-Controlled Home Assistant with AI-powered inference and command execution",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    author="Andy",
    python_requires=">=3.8",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=read_requirements(),
    entry_points={
        'console_scripts': [
            'twin=twin.main:main',
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Home Automation",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    keywords="voice assistant, home automation, AI, speech recognition, smart home",
    project_urls={
        "Documentation": "https://github.com/yourusername/twin",
        "Source": "https://github.com/yourusername/twin",
        "Tracker": "https://github.com/yourusername/twin/issues",
    },
)
