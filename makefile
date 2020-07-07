PYTHON=python
.PHONY: apistub c compile default help messages static test
LOCS=-l fi -l en
MM_ARGS=${LOCS} -i KirppuVenv -i node_modules -i __pycache__ --no-location

# Prefix for some commands to use when not run in activated virtualenv.
ifeq ($(origin VIRTUAL_ENV), undefined)
PFX=./KirppuVenv/bin/
endif

default: help

messages: ## Extract strings from sources for localization.
	DEBUG=1 ${PFX}${PYTHON} manage.py makemessages -d djangojs ${MM_ARGS}
	DEBUG=1 ${PFX}${PYTHON} manage.py makemessages -d django ${MM_ARGS}

static:   ## Install npm dependencies and build static files.
	cd kirppu && npm i && npm run build

compile:  ## Compile localizations for use.
	DEBUG=1 ${PFX}${PYTHON} manage.py compilemessages

c:        ## Clean compiled pyc files.
	find kirppu -name \*.pyc -exec rm {} +
	find kirppuauth -name \*.pyc -exec rm {} +
	find kirppu_project -name \*.pyc -exec rm {} +

apistub:  ## Create/update ajax_api stub file helping navigation from frontend code to backend.
	find kirppu -! -path "kirppu/node_modules*" -name \*.py -exec python3 make_api_stub.py --js kirppu/static_src/js/api_stub.js --py kirppu/tests/api_access.pyi -- {} +

test:     ## Run tests
	DEBUG=1 ${PFX}py.test -vvv

help:     ## This help.
	@fgrep -h "#""#" $(MAKEFILE_LIST) | sed -e "s/:\\s*#""#/\n\t/" -e "s/\\s*#""#/\t/"
