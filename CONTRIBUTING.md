# Contributing to Dave's Domain Monitor

Thank you for your interest in contributing to **Dave's Domain Monitor**! We welcome all contributions, bug reports, and feature requests.

## Development Workflow

1. Fork and clone the repository:
   ```bash
   git clone https://github.com/davidcasanovasola-git/daves-domain-monitor.git
   cd daves-domain-monitor
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   pip install -e .
   ```

3. Run the test suite:
   ```bash
   python3 -m unittest discover -s tests -v
   ```

4. Create a feature branch:
   ```bash
   git checkout -b feature/my-new-feature
   ```

5. Submit a Pull Request.
