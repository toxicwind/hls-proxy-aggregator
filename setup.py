from setuptools import setup, find_packages
setup(name="hls-proxy-aggregator", version="1.0.0", packages=find_packages(), python_requires=">=3.8", install_requires=["aiohttp>=3.9.0", "pyyaml>=6.0"])
