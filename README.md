# OpenVAS docker image

Automatic:
- importing of scan configuration, override configuration, targets and reports
- scan starting
- report saving

## How to build

```
docker build -t openvas .
```

## How to use

Note. Task name must match target name in order for automatic import to be possible.

* Administrator password is defined by OV_PASSWD env variable

```
docker run -d -it \
		-e OV_PASSWD=123456 \
		--name openvas \
		-p 80:80 \
		-p 443:443 \
		-v $(pwd)/configs:/configs:ro \
		-v $(pwd)/targets:/targets:ro \
		-v $(pwd)/tasks:/tasks:ro \
		-v $(pwd)/overrides:/overrides:ro \
		-v $(pwd)/reports:/reports:rw \
		vulnbe/openvas
```

* To enable automatic scan starting pass non-empty OV_AUTORUN_TASKS env variable

```
docker run -e OV_AUTORUN_TASKS=true ...
```

* To enable automatic report saving pass non-empty OV_AUTOSAVE_REPORTS env variable

```
docker run -e OV_AUTOSAVE_REPORTS=true ...
```
