package io.floci.aws.core.common;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.floci.aws.testing.ParallelLocks;
import jakarta.ws.rs.core.HttpHeaders;
import jakarta.ws.rs.core.MultivaluedHashMap;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.core.UriInfo;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.function.Executable;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.net.URI;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ResourceLock(ParallelLocks.PORTS)
class TagDispatcherTest {

    private static final String GROUP = "arn:aws:scheduler:us-east-1:000000000000:schedule-group/reports";
    private static final String REST_API = "arn:aws:apigateway:us-east-1::/restapis/abc123";

    private final TagHandler scheduler = handler("scheduler");
    private final TagHandler apiGateway = handler("apigateway");
    private final TagHandler backup = handler("backup");
    private final TagDispatcher dispatcher = new TagDispatcher(List.of(scheduler, apiGateway, backup),
            new RegionResolver("us-east-1", "000000000000"), new ObjectMapper());

    /**
     * Scheduler, which the generated table reads whole, tags on its modeled /tags/{ResourceArn} alone, the ARN sent
     * as one encoded segment: the bare /tags, or an ARN whose slash is not encoded, is no route of its model and is
     * refused as an ARN that path does not serve, and a method its model does not give on the path as one the path
     * does not take, as Backup's DELETE /tags/{arn} is, Backup untagging on POST /untag/{arn}.
     */
    @Test
    void aServiceTheTableReadsIsServedOnlyOnTheRoutesItsModelGives() {
        String encoded = "/tags/arn%3Aaws%3Ascheduler%3Aus-east-1%3A000000000000%3Aschedule-group%2Freports";
        for (String method : List.of("GET", "POST", "DELETE")) {
            assertSame(scheduler, dispatcher.resolveHandler(GROUP, sent(encoded), method));
        }
        for (String refused : List.of("/tags", "/tags/" + GROUP)) {
            refused(GROUP, () -> dispatcher.resolveHandler(GROUP, sent(refused), "GET"));
        }
        notAllowed(() -> dispatcher.resolveHandler(GROUP, sent(encoded), "PUT"));
        String vault = "arn:aws:backup:us-east-1:000000000000:backup-vault:reports";
        String path = "/tags/arn%3Aaws%3Abackup%3Aus-east-1%3A000000000000%3Abackup-vault%3Areports";
        assertSame(backup, dispatcher.resolveHandler(vault, sent(path), "GET"));
        assertSame(backup, dispatcher.resolveHandler(vault, sent(path), "POST"));
        notAllowed(() -> dispatcher.resolveHandler(vault, sent(path), "DELETE"));
    }

    private static void notAllowed(Executable resolve) {
        AwsException error = assertThrows(AwsException.class, resolve);
        assertEquals(405, error.getHttpStatus());
        assertEquals("MethodNotAllowedException", error.getErrorCode());
    }

    private static void refused(String arn, Executable resolve) {
        AwsException error = assertThrows(AwsException.class, resolve);
        assertEquals(400, error.getHttpStatus());
        assertEquals("Invalid resource ARN: " + arn, error.getMessage());
    }

    /**
     * API Gateway is still built by hand, its tagged ARN read wherever the controller reads it, so every route serves
     * it.
     */
    @Test
    void aServiceBuiltByHandIsServedOnEveryRoute() {
        assertSame(apiGateway, dispatcher.resolveHandler(REST_API, sent("/tags"), "GET"));
        assertSame(apiGateway, dispatcher.resolveHandler(REST_API, sent("/tags/" + REST_API), "PUT"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"garbage", "{}", "null"})
    void strictTaggingRejectsTrailingTokensBeforeCallingTheService(String trailing) {
        when(scheduler.strictTagValidation()).thenReturn(true);
        when(scheduler.tagsBodyKey()).thenReturn("tags");
        when(scheduler.tagValidationErrorCode()).thenReturn("ValidationException");
        HttpHeaders headers = mock(HttpHeaders.class);
        try (Response success = Response.ok().build()) {
            AwsException error = assertThrows(AwsException.class,
                    () -> dispatcher.tagResourcePost(headers, GROUP, "{\"tags\":{\"team\":\"ops\"}} " + trailing, success));
            assertEquals("ValidationException", error.getErrorCode());
            assertEquals(400, error.getHttpStatus());
            verify(scheduler, never()).tagResource(any(), any(), anyMap());
        }
    }

    @Test
    void strictParsingDoesNotChangeTheInjectedMapperOrLenientHandlers() {
        when(scheduler.strictTagValidation()).thenReturn(true);
        when(scheduler.tagsBodyKey()).thenReturn("tags");
        when(apiGateway.tagsBodyKey()).thenReturn("tags");
        HttpHeaders headers = mock(HttpHeaders.class);
        try (Response success = Response.ok().build()) {
            String body = "{\"tags\":{\"team\":\"ops\"}}";
            assertSame(success, dispatcher.tagResourcePost(headers, GROUP, body, success));
            assertSame(success, dispatcher.tagResourcePost(headers, REST_API, body + " {}", success));
            verify(scheduler).tagResource("us-east-1", GROUP, Map.of("team", "ops"));
            verify(apiGateway).tagResource("us-east-1", REST_API, Map.of("team", "ops"));
        }
    }

    private static TagHandler handler(String serviceKey) {
        TagHandler handler = mock(TagHandler.class);
        when(handler.serviceKey()).thenReturn(serviceKey);
        return handler;
    }

    /** The URI of a request sent to the path, as {@link UriInfo} gives it. */
    private static UriInfo sent(String path) {
        UriInfo uriInfo = mock(UriInfo.class);
        when(uriInfo.getRequestUri()).thenReturn(URI.create("http://localhost:4566" + path));
        when(uriInfo.getBaseUri()).thenReturn(URI.create("http://localhost:4566/"));
        when(uriInfo.getQueryParameters()).thenReturn(new MultivaluedHashMap<>());
        return uriInfo;
    }
}
