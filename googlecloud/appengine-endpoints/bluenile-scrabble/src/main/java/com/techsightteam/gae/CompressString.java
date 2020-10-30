package com.techsightteam.gae;

import java.io.*;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

public class CompressString {
    public static String decompressString(byte[] bytes) throws IOException, ClassNotFoundException {
        String dictWords;
        ByteArrayInputStream bais = new ByteArrayInputStream(bytes);
        GZIPInputStream gzipIn = new GZIPInputStream(bais);
        ObjectInputStream objectIn = new ObjectInputStream(gzipIn);
        dictWords = (String) objectIn.readObject();
        objectIn.close();
        return dictWords;
    }

    public static byte[] compressString(String dictWords) throws IOException {
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        GZIPOutputStream gzipOut = new GZIPOutputStream(baos);
        ObjectOutputStream objectOut = new ObjectOutputStream(gzipOut);
        objectOut.writeObject(dictWords);
        objectOut.close();
        return baos.toByteArray();
    }
}
