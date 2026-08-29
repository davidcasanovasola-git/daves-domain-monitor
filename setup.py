from setuptools import setup, find_packages

setup(
    name="daves-domain-monitor",
    version="1.0.0",
    description="Dave's Domain Monitor - Automated Domain Availability Sniper & 1-Click Cloudflare Registrar Bot",
    author="Dave",
    packages=find_packages(),
    install_requires=[
        "requests>=2.25.0",
        "PyYAML>=5.4.0",
    ],
    entry_points={
        "console_scripts": [
            "domain-monitor = domain_monitor.cli:main",
            "ddm = domain_monitor.cli:main",
        ],
    },
    python_requires=">=3.8",
)
