#
# Basic makefile for general targets
#
PACKAGE = @@project_name@@
MODULE = @@python_module@@

##
## NOTE: Anything changed below this line should be changed in base_service.git
## and then merged into individual projects.  This prevents conflicts and
## maintains consistency between projects.
##
COVERAGE = bin/coverage
COVERAGE_ARGS = --with-coverage --cover-package=$(MODULE) --cover-tests --cover-erase
DEVELOPMENT_ENV = source bin/activate; $(shell echo $(PACKAGE) | tr 'a-z\-' 'A-Z_')_CONF=configuration/development.conf
APT_REQ_FILE = requirements.apt
DIST_FILE = dist/$(PACKAGE)-$(VERSION).tar.gz
EASY_INSTALL = bin/easy_install
IPYTHON = bin/ipython
NOSE = bin/nosetests
NOSYD = bin/nosyd -1
PIP = C_INCLUDE_PATH="/opt/local/include:/usr/local/include" bin/pip
PIP_OPTIONS = --index-url=http://pypi.colo.lair/simple/
PYREVERSE = pyreverse -o png -p
PYTHON = bin/python
PYTHON_DOCTEST = $(PYTHON) -m doctest
SCP = scp
# Work around a bug in git describe: http://comments.gmane.org/gmane.comp.version-control.git/178169
VERSION = $(shell git status >/dev/null 2>/dev/null && git describe --abbrev=6 --tags --dirty --match="v*" | cut -c 2-)

## Testing ##
.PHONY: test unit-test integration-test system-test acceptance-test tdd coverage coverage-html
test: unit-test integration-test system-test acceptance-test
unit-test: reports
	$(DEVELOPMENT_ENV) $(NOSE) unit --with-xunit --xunit-file=reports/unit-xunit.xml

integration-test: reports
	$(DEVELOPMENT_ENV) $(NOSE) integration --with-xunit --xunit-file=reports/integration-xunit.xml

system-test: reports
	$(DEVELOPMENT_ENV) $(NOSE) system --with-xunit --xunit-file=reports/system-xunit.xml

acceptance-test: reports
	$(DEVELOPMENT_ENV) $(NOSE) acceptance --with-xunit --xunit-file=reports/acceptance-xunit.xml

tdd:
	$(DEVELOPMENT_ENV) $(NOSYD)

coverage: reports
	$(DEVELOPMENT_ENV) $(NOSE) $(COVERAGE_ARGS) --cover-package=tests.unit unit
	$(COVERAGE) xml -o reports/unit-coverage.xml --include="*.py"

integration-coverage: reports
	$(DEVELOPMENT_ENV) $(NOSE) $(COVERAGE_ARGS) --cover-package=tests.integration integration
	$(COVERAGE) xml -o reports/integration-coverage.xml --include="*.py"

coverage-html:
	$(COVERAGE) html

reports:
	mkdir -p $@


## Documentation ##
.PHONY: doc
doc: RELEASE-VERSION
	$(PYTHON) setup.py build_sphinx

## Static analysis ##
.PHONY: lint uml metrics pep8 pylint
lint: pylint pep8
pylint: reports tests.pylintrc
	-bin/pylint --reports=y --output-format=parseable --rcfile=pylintrc $(MODULE) | tee reports/$(MODULE)_pylint.txt
	-bin/pylint --reports=y --output-format=parseable --rcfile=tests.pylintrc tests | tee reports/tests_lint.txt

tests.pylintrc: pylintrc pylintrc-tests-overrides
	cat $^ > $@

pep8: reports
	# Strip out warnings about long lines in tests. We loosen the
	# limitation for long lines in tests and PyLint already checks line
	# length for us.
	-bin/pep8 --filename="*.py" --repeat $(MODULE) tests | grep -v '^tests/.*E501' | tee reports/pep8.txt


## Local Setup ##
requirements: virtualenv clean-requirements
	$(EASY_INSTALL) -U distribute
	# need ports libevent and libevent1 for mac_dev
	-test -e $(HOME)/.requirements.pip && $(PIP) install $(PIP_OPTIONS) -r $(HOME)/.requirements.pip
	$(PIP) install $(PIP_OPTIONS) -r requirements.pip
	-rm README.txt
	# These libs don't work when installed via pip.
	$(EASY_INSTALL) readline

virtualenv:
	virtualenv --distribute --no-site-packages --python=python2.6 .

clean-requirements:
	-rm -rf src


.PHONY: foreman
foreman:
	$(DEVELOPMENT_ENV) PYTHON_LOGCONFIG_LOG_TO_STDOUT=1 foreman start


## Packaging ##
.PHONY: RELEASE-VERSION
RELEASE-VERSION:
	echo $(VERSION) > $@

.PHONY: dist upload $(DIST_FILE)
dist: $(DIST_FILE)
$(DIST_FILE): RELEASE-VERSION
	$(PYTHON) setup.py sdist

upload: dist
	@if echo $(VERSION) | grep -q dirty; then \
	    echo "Stubbornly refusing to upload a dirty package! Tag a proper release!" >&2; \
	    exit 1; \
	fi
	$(PYTHON) setup.py register --repository aweber sdist upload --repository aweber

deploy-docs: $(PACKAGE)_docs.tar.gz
	fab set_documentation_host deploy_docs:$(PACKAGE),`cat RELEASE-VERSION` -u ubuntu

$(PACKAGE)_docs.tar.gz: doc
	cd doc/html; tar czf ../../$@ *


## Housekeeping ##
clean:
	# clean python bytecode files
	-find . -type f -name '*.pyc' -o -name '*.tar.gz' | xargs rm -f
	-rm -f pip-log.txt
	-rm -f .nose-stopwatch-times .coverage
	-rm -rf reports
	-rm -f nosetests.xml
	#
	-rm -rf build dist tmp uml/* *.egg-info RELEASE-VERSION htmlcov

maintainer-clean: clean
	rm -rf bin include lib man share src doc/doctrees doc/html

## Service Deployment ##
.PHONY: deploy-staging deploy-production
deploy-staging: dist Procfile
	caterer staging $(PACKAGE) Procfile > chef_script; sh chef_script
	fab set_hosts:'staging','api' deploy_api:'$(DIST_FILE)','$(APT_REQ_FILE)' -u ubuntu

deploy-production: dist Procfile
	caterer production $(PACKAGE) Procfile > chef_script; sh chef_script
	fab set_hosts:'production','api' deploy_api:'$(DIST_FILE)','$(APT_REQ_FILE)' -u ubuntu

deploy-vagrant: dist
	fab set_hosts:'vagrant','api' deploy_api:'$(DIST_FILE)','$(APT_REQ_FILE)' -u vagrant -p vagrant

create-vagrant-env: Procfile
	caterer vagrant $(PACKAGE) Procfile > chef_script; sh chef_script

chef-roles: Procfile
	caterer production $(PACKAGE) Procfile > /dev/null
