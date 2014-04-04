override PYTHON_VERSION = python3.4

.PHONY: server
server: 
	$(PYTHON) $(MODULE)/app.py
