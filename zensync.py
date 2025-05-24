#!/usr/bin/env python3
import logging
from cli import run_cli

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def main():
    """Main entry point"""
    run_cli()

if __name__ == "__main__":
    main() 
