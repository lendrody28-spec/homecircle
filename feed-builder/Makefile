PYTHONPATH := src
export PYTHONPATH

.PHONY: test build sources

test:
	python3 -m unittest discover -s tests -v

build:
	python3 -m homecircle_feed build --refresh

sources:
	python3 -m homecircle_feed sources
