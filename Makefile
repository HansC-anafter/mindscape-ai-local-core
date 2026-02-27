PYTHONPATH := $(PWD):$(PWD)/backend:$(PWD)/backend/app

.PHONY: test test-l2 test-l3

test:
	PYTHONPATH=$(PYTHONPATH) python -m pytest backend/tests/ -v

test-l2:
	PYTHONPATH=$(PYTHONPATH) python -m pytest backend/tests/services/orchestration/ -v -m "not l3"

test-l3:
	PYTHONPATH=$(PYTHONPATH) python -m pytest backend/tests/services/orchestration/ -v -m l3
