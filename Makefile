SERVICE=openvas
REPO=vulnbe
TAG=10

.PHONY: image test all push tag

all: image push

image:
	docker build \
		--build-arg version=10 \
		--build-arg openvas_scanner="v6.0.0.tar.gz" \
		--build-arg gvm_libs="v10.0.0.tar.gz" \
		--build-arg gvmd="v8.0.0.tar.gz" \
		--build-arg gsa="v8.0.0.tar.gz" \
		-t $(SERVICE):$(TAG) .

push: tag
	docker push $(REPO)/$(SERVICE):$(TAG)

tag:
	docker tag $(SERVICE):$(TAG) $(REPO)/$(SERVICE):$(TAG)

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
