FUNCTIONS_PATH = ./src/code
ZIP_PATH = ./src/code/archived

all: zip_lambdas cdkdeploy cdkoutput


deploy: zip_lambdas cdkdeploy

zip_lambdas:
	$(foreach file, $(wildcard $(FUNCTIONS_PATH)/*.py), zip -j $(ZIP_PATH)/$(basename $(notdir $(file))).zip $(file);)


cdkdeploy:
	cdktf deploy

cdkoutput:
	cdktf output --outputs-file outputs.json --outputs-file-include-sensitive-outputs true

destroy:
	cdktf destroy