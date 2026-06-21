"""Setup configuration for openinsider package."""

from setuptools import find_packages, setup

setup(
    name="openinsider",
    version="0.2.0",
    packages=find_packages(),
    install_requires=[
        "pydantic>=2.0.0",
        "python-dotenv>=1.0.0",
        "requests>=2.31.0",
        "beautifulsoup4>=4.12.0",
        "lxml>=4.9.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "pytest-mock>=3.12.0",
        ],
    },
    python_requires=">=3.11",
)
