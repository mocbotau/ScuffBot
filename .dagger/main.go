package main

import (
	"context"

	"dagger/scuffbot/internal/dagger"
)

const (
	repoName      = "scuffbot"
)

type Scuffbot struct {
	// Source code directory
	Source *dagger.Directory
	// +private
	InfisicalClientSecret *dagger.Secret
}

func New(
	// Source code directory
	// +defaultPath="."
	source *dagger.Directory,
	infisicalClientSecret *dagger.Secret,
) *Scuffbot {
	return &Scuffbot{
		Source:                source,
		InfisicalClientSecret: infisicalClientSecret,
	}
}

// BuildAndPush builds and pushes the Docker image to the container registry
func (m *Scuffbot) BuildAndPush(
	ctx context.Context,
	// Environment to build image for
	// +default="staging"
	env string,
) (string, error) {
	docker := dag.Docker(m.Source, m.InfisicalClientSecret, repoName, dagger.DockerOpts{
		Environment: env,
	})

	return docker.Build().Publish(ctx)
}
