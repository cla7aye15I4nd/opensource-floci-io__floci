package io.floci.aws.services.backup;

import io.floci.aws.core.common.StoredResourceArns;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;

import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * What IAM asks Backup of the resources a request names: the tags Backup holds on a backup vault or a backup plan,
 * which an {@code aws:ResourceTag} condition reads.
 */
@ApplicationScoped
public class BackupStoredResourceArns implements StoredResourceArns {

    private final BackupService backup;

    @Inject
    public BackupStoredResourceArns(BackupService backup) {
        this.backup = backup;
    }

    @Override
    public String namespace() {
        return "backup";
    }

    /** Backup stores no resource a request names but by its ARN or its format's variables: a plan's id it mints. */
    @Override
    public Optional<String> find(String type, List<String> names, String region) {
        return Optional.empty();
    }

    @Override
    public Map<String, String> storedTags(String arn) {
        return backup.storedTags(arn);
    }
}
