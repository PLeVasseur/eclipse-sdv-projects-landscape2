# Eclipse SDV Projects - Landscape2

Creates a static site via the [Landscape2] project for the Eclipse SDV Projects.

## Build

Prerequisites: ensure you've got Docker Compose installed

```shell
docker compose --env-file .env.stable run --rm l2-build
```

## Serve

Prerequisites: ensure you've got Docker Compose installed

```shell
docker compose --env-file .env.stable run --rm l2-serve
```

## Extracting built site


```shell
mkdir -p build
docker compose run --rm l2-export | tar -C build -xf -
```

## Note on stable and latest

Any command above can also be run using `--env-file .env.latest`
to use the latest available distributed [Landscape2] Docker image.

For example:
```shell
docker compose --env-file .env.latest run --rm l2-build
```

[Landscape2]: https://github.com/cncf/landscape2

# Collect new data from Eclipse Projects API (with static categories)
Hint: execute in the root folder
Modifiy the static_categories.yml to map all the projects static. 
```shell
python ./tools/generate_data_static.py --categories static_categories.yml --output data.yml 
```


