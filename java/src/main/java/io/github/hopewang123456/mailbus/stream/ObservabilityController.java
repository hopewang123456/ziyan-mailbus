package io.github.hopewang123456.mailbus.stream;

import io.github.hopewang123456.mailbus.observability.ObservabilityDtos;
import io.github.hopewang123456.mailbus.observability.OverviewService;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.http.MediaType;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;

@RestController
@RequestMapping("/api")
@Validated
public class ObservabilityController {

    private final OverviewService overviewService;
    private final StreamService streamService;

    public ObservabilityController(OverviewService overviewService,
                                   StreamService streamService) {
        this.overviewService = overviewService;
        this.streamService = streamService;
    }

    @GetMapping("/overview")
    public ObservabilityDtos.OverviewOut overview() {
        return overviewService.get();
    }

    @GetMapping("/log")
    public List<ObservabilityDtos.LogEntryOut> log(
            @RequestParam(defaultValue = "50") @Min(1) @Max(500) int limit) {
        return overviewService.log(limit);
    }

    @GetMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream() {
        return streamService.subscribe();
    }
}
