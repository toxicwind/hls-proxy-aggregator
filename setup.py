from setuptools import setup, find_packages
setup(name="hls-proxy-aggregator", version="1.0.0", description="Netflix-grade HLS proxy aggregator", author="toxicwind", python_requires=">=3.8", packages=find_packages(), install_requires=["aiohttp>=3.9.0", "pyyaml>=6.0"], entry_points={"console_scripts": ["hls-proxy=src.main:main"]})
