SERVICE=openvas
REPO=vulnbe
TAG=9

.PHONY: image test all push tag

all: image push

image:
	docker build \
		--build-arg version=9 \
		--build-arg openvas_scanner="v5.1.3.tar.gz" \
		--build-arg gvm_libs="v9.0.3.tar.gz" \
		--build-arg gvmd="v7.0.3.tar.gz" \
		--build-arg gsa="v7.0.3.tar.gz" \
		-t $(SERVICE):$(TAG) .

push: tag
	docker push $(REPO)/$(SERVICE):$(TAG)
	docker push $(REPO)/$(SERVICE):latest

tag:
	docker tag $(SERVICE):$(TAG) $(REPO)/$(SERVICE):$(TAG)
	docker tag $(SERVICE):$(TAG) $(REPO)/$(SERVICE):latest

rm:
	docker rm -f $(SERVICE)

test_run:
	docker run -d -it \
		-e OV_PASSWD=123456 \
		-e OV_AUTORUN_TASKS=true \
		-e OV_AUTOSAVE_REPORTS=true \
		-p 80:80 \
		-p 443:443 \
		-v $(shell pwd)/configs:/configs:ro \
		-v $(shell pwd)/targets:/targets:ro \
		-v $(shell pwd)/tasks:/tasks:ro \
		-v $(shell pwd)/overrides:/overrides:rw \
		-v $(shell pwd)/reports:/reports:rw \
		--name $(SERVICE) \
		$(SERVICE):$(TAG)
