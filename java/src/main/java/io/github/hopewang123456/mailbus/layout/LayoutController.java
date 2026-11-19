package io.github.hopewang123456.mailbus.layout;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class LayoutController {

    private final LayoutService service;

    public LayoutController(LayoutService service) {
        this.service = service;
    }

    @GetMapping("/layout")
    public LayoutDtos.OfficeSiteOut layout() {
        return service.get();
    }

    @GetMapping("/public/layout")
    public LayoutDtos.PublicOfficeSiteOut publicLayout() {
        return service.getPublic();
    }
}
