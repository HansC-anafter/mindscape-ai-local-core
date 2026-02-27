#!/bin/bash

# Create user and databases
psql -d postgres -c "CREATE USER mindscape WITH PASSWORD 'mindscape_password';" > /dev/null 2>&1
psql -d postgres -c "CREATE DATABASE mindscape_core;" > /dev/null 2>&1
psql -d postgres -c "CREATE DATABASE mindscape_vectors;" > /dev/null 2>&1

export DATABASE_URL=postgresql://mindscape:mindscape_password@localhost:5432/mindscape_core
export DATABASE_URL_CORE=postgresql://mindscape:mindscape_password@localhost:5432/mindscape_core
export DATABASE_URL_VECTOR=postgresql://mindscape:mindscape_password@localhost:5432/mindscape_vectors

export POSTGRES_DB=mindscape_vectors
export POSTGRES_USER=mindscape
export POSTGRES_PASSWORD=mindscape_password
export LOCAL_AUTH_SECRET=dev-secret-key-change-in-production
export LOG_LEVEL=INFO
export ENABLE_LLM_INTENT_EXTRACTOR=true
export OCR_USE_GPU=false
export OCR_LANG=ch
export TZ=UTC

# Unset all other postgres variables
unset POSTGRES_CORE_HOST
unset POSTGRES_CORE_PORT
unset POSTGRES_CORE_DB
unset POSTGRES_CORE_USER
unset POSTGRES_CORE_PASSWORD
unset POSTGRES_VECTOR_HOST
unset POSTGRES_VECTOR_PORT
unset POSTGRES_VECTOR_DB
unset POSTGRES_VECTOR_USER
unset POSTGRES_VECTOR_PASSWORD
unset POSTGRES_HOST
unset POSTGRES_PORT

export PYTHONPATH=$PYTHONPATH:.
pytest
