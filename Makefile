SERVICE=openvas
REPO=vulnbe
TAG=10-beta2

.PHONY: image test all push tag

all: image push

image:
	docker build -t $(SERVICE):$(TAG) .

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
		-p 127.0.0.1:80:80 \
		-p 127.0.0.1:443:443 \
		-v $(shell pwd)/configs:/configs:ro \
		-v $(shell pwd)/targets:/targets:ro \
		-v $(shell pwd)/tasks:/tasks:ro \
		-v $(shell pwd)/overrides:/overrides:rw \
		-v $(shell pwd)/reports:/reports:rw \
		--name $(SERVICE) \
		$(SERVICE):$(TAG)
