.PHONY: dev test lint bootstrap

bootstrap:
	bash scripts/bootstrap.sh

dev:
	bash scripts/dev.sh

test:
	bash scripts/test.sh

lint:
	bash scripts/lint.sh
