package main

import (
	"context"

	"dagger/scuffbot/internal/dagger"
)

const (
	repoName      = "scuffbot"
	pythonVersion = "3.10"
)

type Scuffbot struct {
	// Source code directory
	Source *dagger.Directory
	// +private
	PythonVersion string
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
		PythonVersion:         pythonVersion,
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
