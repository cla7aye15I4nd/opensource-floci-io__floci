package io.floci.aws.services.appsync;

import io.floci.aws.core.common.StoredResourceArns;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;

import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * What IAM asks AppSync of the resources a request names: the tags AppSync holds on a GraphQL API or a custom domain
 * name, which an {@code aws:ResourceTag} condition reads.
 */
@ApplicationScoped
public class AppSyncStoredResourceArns implements StoredResourceArns {

    private final AppSyncService appSync;

    @Inject
    public AppSyncStoredResourceArns(AppSyncService appSync) {
        this.appSync = appSync;
    }

    @Override
    public String namespace() {
        return "appsync";
    }

    /** AppSync stores no resource under a name a request fills an ARN with: an API's id is one it mints. */
    @Override
    public Optional<String> find(String type, List<String> names, String region) {
        return Optional.empty();
    }

    @Override
    public Map<String, String> storedTags(String arn) {
        return appSync.storedTags(arn);
    }
}
