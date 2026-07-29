#!/usr/bin/env bash

install_python() {

    info "Creating Python virtual environment..."

    if [[ ! -d venv ]]; then
        python3 -m venv venv
        success "Virtual environment created."
    else
        warning "Virtual environment already exists."
    fi

    info "Activating virtual environment..."

    source venv/bin/activate

    info "Upgrading pip..."

    pip install --upgrade pip

    info "Installing Python packages..."

    pip install -r requirements.txt

    success "Python environment ready."

}
