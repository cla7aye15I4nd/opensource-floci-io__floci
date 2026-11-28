package io.floci.aws.services.eventbridge;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.floci.aws.core.common.AwsException;
import io.floci.aws.core.common.RegionResolver;
import io.floci.aws.core.storage.AccountAwareStorageBackend;
import io.floci.aws.core.storage.InMemoryStorage;
import io.floci.aws.services.eventbridge.model.Connection;
import org.junit.jupiter.api.Test;

import java.util.Optional;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.when;

/**
 * The secret a connection keeps its credentials in, which a Step Functions HTTP task's permissions ask for. A
 * connection saved before stores kept accounts apart sits under a bare key of the default account; the HTTP call
 * itself still finds it, so the permission lookup must too, without moving it.
 */
class EventBridgeConnectionSecretLookupTest {
    private static final String ACCOUNT = "000000000000";
    private static final String REGION = "us-east-1";
    private static final String CONNECTION_ARN = "arn:aws:events:" + REGION + ":" + ACCOUNT + ":connection/saved/abc";
    private static final String SECRET_ARN = "arn:aws:secretsmanager:" + REGION + ":" + ACCOUNT
            + ":secret:events!connection/saved/abc-XyZ";

    @Test
    void aConnectionSavedUnderABareKeyStillNamesItsSecretAndStaysWhereItIs() {
        InMemoryStorage<String, Connection> raw = new InMemoryStorage<>();
        String bareKey = "connection:" + REGION + ":saved";
        raw.put(bareKey, connection());
        EventBridgeService service = service(new AccountAwareStorageBackend<>(raw, null, ACCOUNT));

        assertEquals(Optional.of(SECRET_ARN), service.recorded(CONNECTION_ARN, "SecretArn"));
        assertEquals(Set.of(bareKey), raw.keys());
    }

    @Test
    void aConnectionOfAnotherAccountUnderABareKeyNamesNoSecret() {
        InMemoryStorage<String, Connection> raw = new InMemoryStorage<>();
        raw.put("connection:" + REGION + ":saved", connection());
        EventBridgeService service = service(new AccountAwareStorageBackend<>(raw, null, ACCOUNT));

        assertEquals(Optional.empty(), service.recorded(CONNECTION_ARN.replace(ACCOUNT, "222222222222"), "SecretArn"));
    }

    /**
     * A connection is its own account's: a request of another account naming it finds nothing, and does not move
     * the default account's legacy connection into its own partition, where the secret lookup, which reads the
     * account the ARN names, would no longer find it while the call still used it.
     */
    @Test
    void anotherAccountNeitherUsesNorMovesTheDefaultAccountsLegacyConnection() {
        InMemoryStorage<String, Connection> raw = new InMemoryStorage<>();
        String bareKey = "connection:" + REGION + ":saved";
        raw.put(bareKey, connection());
        RegionResolver otherAccount = spy(new RegionResolver(REGION, ACCOUNT));
        when(otherAccount.getAccountId()).thenReturn("222222222222");
        EventBridgeService service = service(new AccountAwareStorageBackend<>(raw, null, ACCOUNT), otherAccount);

        assertThrows(AwsException.class, () -> service.findConnectionByArn(CONNECTION_ARN, REGION));

        assertEquals(Set.of(bareKey), raw.keys());
        assertEquals(Optional.of(SECRET_ARN), service.recorded(CONNECTION_ARN, "SecretArn"));
    }

    /** The default account's own call still finds its legacy connection, and the secret lookup agrees. */
    @Test
    void theDefaultAccountsCallFindsItsLegacyConnectionAndTheSecretLookupStillAgrees() {
        InMemoryStorage<String, Connection> raw = new InMemoryStorage<>();
        raw.put("connection:" + REGION + ":saved", connection());
        EventBridgeService service = service(new AccountAwareStorageBackend<>(raw, null, ACCOUNT));

        assertEquals(CONNECTION_ARN, service.findConnectionByArn(CONNECTION_ARN, REGION).getConnectionArn());

        assertEquals(Optional.of(SECRET_ARN), service.recorded(CONNECTION_ARN, "SecretArn"));
    }

    private static Connection connection() {
        Connection connection = new Connection();
        connection.setName("saved");
        connection.setConnectionArn(CONNECTION_ARN);
        connection.setSecretArn(SECRET_ARN);
        return connection;
    }

    private static EventBridgeService service(AccountAwareStorageBackend<Connection> connections) {
        return service(connections, new RegionResolver(REGION, ACCOUNT));
    }

    private static EventBridgeService service(AccountAwareStorageBackend<Connection> connections,
                                              RegionResolver regions) {
        return new EventBridgeService(new InMemoryStorage<>(), new InMemoryStorage<>(), new InMemoryStorage<>(),
                new InMemoryStorage<>(), new InMemoryStorage<>(), new InMemoryStorage<>(), connections,
                new InMemoryStorage<>(), regions, new ObjectMapper(), null, null, null, null, null, null);
    }
}
