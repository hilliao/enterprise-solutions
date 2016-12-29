import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.*;
import org.springframework.stereotype.*;
import org.springframework.web.bind.annotation.*;

import java.util.concurrent.Callable;

@RestController
@EnableAutoConfiguration
public class Example {

    @RequestMapping("/")
    @CrossOrigin
    String home() {
        Callable<Integer> task = () -> {
            return Integer.valueOf(1);
        };
        return "Hello World! from springboot";
    }

    public static void main(String[] args) throws Exception {
        SpringApplication.run(Example.class, args);
    }

}