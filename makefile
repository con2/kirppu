PYTHON := python
LANGUAGES := fi en
PYTEST_ARGS := -vvv
UV := uv

# Optionally include user variables.
sinclude makevars

MM_ARGS = $(foreach lang, ${LANGUAGES}, -l ${lang}) -i KirppuVenv -i .venv -i node_modules --no-location $(foreach ignore, ${MM_IGNORES}, -i ${ignore})

# Prefix for some commands to use when not run in activated virtualenv.
ifeq ($(origin VIRTUAL_ENV), undefined)
PFX := ./.venv/bin/
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

cloc:     ## Count project lines using cloc.
	cloc --git HEAD --exclude-ext=po

apistub:  ## Create/update ajax_api stub file helping navigation from frontend code to backend.
	find kirppu -! -path "kirppu/node_modules*" -name \*.py -exec python3 make_api_stub.py --js kirppu/static_src/js/api_stub.js --py kirppu/tests/api_access.pyi -- {} +

test:     ## Run tests
	DEBUG=1 ${PFX}py.test ${PYTEST_ARGS}

update: update-sync update-requirements  ## Update packages and export requirements

update-sync:  ## Update packages and lockfile
	${UV} sync --all-extras -U

update-requirements:  ## Generate requirements-* files.
	${UV} export --extra dev -o requirements-dev.txt
	${UV} export --extra oauth --extra production -o requirements-production.txt

venv:  ## Create virtualenv (.venv) using uv
	${UV} sync --extra dev --frozen --no-python-downloads --verbose

help:     ## This help.
	@grep -F -h "#""#" $(MAKEFILE_LIST) | sed -e "s/:.*#""#/\n\t/" -e "s/\\s*#""#/\t/"

.PHONY: apistub c cloc compile default help messages requirement-sets static test update-constraints
