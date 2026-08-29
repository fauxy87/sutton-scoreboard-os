#!/usr/bin/env bash

install_python() {

    info "Creating Python virtual environment..."

    if [[ ! -d venv ]]; then
        python3 -m venv --system-site-packages venv
        success "Virtual environment created."
    else
        info "Refreshing existing virtual environment..."
        python3 -m venv \
            --upgrade \
            --system-site-packages \
            venv
        success "Virtual environment refreshed."
    fi

    info "Activating virtual environment..."

    info "Upgrading pip..."

    venv/bin/python -m pip install --upgrade pip

    info "Installing Python packages..."

    venv/bin/python -m pip install -r requirements.txt

    success "Python environment ready."

}
