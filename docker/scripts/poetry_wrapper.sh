#!/bin/bash

poetry run "$@" 2>&1 | grep -v "Skipping virtualenv creation"
exit "${PIPESTATUS[0]}"
