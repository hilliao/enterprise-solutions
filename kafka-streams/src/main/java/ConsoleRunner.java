import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.apache.kafka.common.serialization.Deserializer;
import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.serialization.Serializer;
import org.apache.kafka.connect.json.JsonDeserializer;
import org.apache.kafka.connect.json.JsonSerializer;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KStreamBuilder;
import org.apache.kafka.streams.processor.AbstractProcessor;

import java.util.Properties;

public class ConsoleRunner {

    public static final String TOPIC = "clickstream.client.analytics.track.raw.v1";

    public static void main(final String[] args) throws Exception {
        Properties settings = new Properties();
        settings.put(StreamsConfig.APPLICATION_ID_CONFIG, "complex-event-processing");
        settings.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "lxzzkb01.qa.ocean.com:9092");
        final Serializer<JsonNode> jsonNodeSerializer = new JsonSerializer();
        final Deserializer<JsonNode> jsonNodeDeserializer = new JsonDeserializer();
        final Serde<JsonNode> jsonSerde = Serdes.serdeFrom(jsonNodeSerializer, jsonNodeDeserializer);
        settings.put(StreamsConfig.KEY_SERDE_CLASS_CONFIG, Serdes.String().getClass().getName());
        settings.put(StreamsConfig.VALUE_SERDE_CLASS_CONFIG, Serdes.String().getClass().getName());

        KStreamBuilder builder = new KStreamBuilder();
        KStream<String, JsonNode> personalizationStream = builder.stream(Serdes.String(), jsonSerde, TOPIC);

        // sample code 1 of enriching events: KStream<String, JsonNode> richEventStream = personalizationStream.mapValues(ClientEvent::addVideoTitleRatingGenre)

        // sample code 2 of enriching events: change to {"_eventType":"complex event type" for events of "location":"deck"
        personalizationStream.process(() -> new AbstractProcessor<String, JsonNode>() {
            @Override
            public void process(String s, JsonNode jsonNode) {
                System.out.println("KStream key: " + s);
                System.out.println("KStream value: " + jsonNode);
                if (jsonNode.get("location").asText().equals("deck")) {
                    ((ObjectNode) jsonNode).put("_eventType", "complex event type");
                }
            }
        });

        /*
         * post events back to Kafka with a different topic
         * use the following command to test listening on the riched events:
         * export KAFKA_SERVER=lxzzkb01.qa.ocean.com:9092 &&
         * kafka-console-consumer --topic clickstream.client.personalization.content_selection.rich.v1  --bootstrap-server $KAFKA_SERVER &
         */
        personalizationStream.to(Serdes.String(), jsonSerde, "clickstream.client.personalization.content_selection.rich.v1");
        KafkaStreams streams = new KafkaStreams(builder, settings);
        streams.start();

        Runtime.getRuntime().addShutdownHook(new Thread(streams::close));
    }
}
