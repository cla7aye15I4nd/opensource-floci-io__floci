package io.floci.aws.testing;

import io.floci.aws.core.common.RequestScopes;
import io.floci.aws.services.ecr.registry.EcrRegistryManager;
import io.quarkus.arc.Arc;

import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Starts the ECR registry before a stack creates a repository: {@code CreateRepository} starts it inside the request,
 * which can take longer than the stack wait. Without Docker there is no registry to start and nothing to wait for.
 */
public final class EcrRegistryWarmup {

    private EcrRegistryWarmup() {
    }

    public static void warm() {
        if (!dockerAvailable()) {
            return;
        }
        EcrRegistryManager registryManager = Arc.container().instance(EcrRegistryManager.class).get();
        boolean started = RequestScopes.callAs(null, "us-west-2", registryManager::tryEnsureStarted);
        assertTrue(started, "ECR registry failed to start");
    }

    private static boolean dockerAvailable() {
        try {
            return DockerAvailability.isAvailable();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted while probing Docker", e);
        }
    }
}
