package com.dlinkddns.hil.sunshine;

import android.support.v4.app.Fragment;
import android.os.Bundle;
import android.view.Gravity;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.ListView;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * A placeholder fragment containing a simple view.
 */
public class MainActivityFragment extends Fragment {

    public MainActivityFragment() {
    }

    @Override
    public View onCreateView(LayoutInflater inflater, ViewGroup container,
                             Bundle savedInstanceState) {
        View fragView = inflater.inflate(R.layout.fragment_main, container, false);
        List<String> weekForecast = new ArrayList<>(Arrays.asList(
                "Today - sunney - 11/1C - 1/29",
                "Tomorrow - sunney - 11/5C - 1/30",
                "Wednesday- cloudy - 13/4C - 1/31",
                "Thursday- rain - 9/1C - 2/01",
                "Friday- rain- 12/2C - 2/02",
                "Saturday- shower- 11/3C - 2/03",
                "Sunday- intermittent clouds - 13/3C - 2/04"));
        weekForecast.addAll(weekForecast);
        ArrayAdapter<String> forecastAdapter = new ArrayAdapter<String>(
                this.getActivity(), R.layout.list_item_forecast, R.id.list_item_forecast_textview, weekForecast);
        ListView forecastListView = (ListView) fragView.findViewById(R.id.listView_forecast);
        forecastListView.setAdapter(forecastAdapter);
        TextView weatherTextView = (TextView) fragView.findViewById(R.id.list_item_forecast_textview);
        //weatherTextView.setGravity(Gravity.CENTER);
        return fragView;
    }
}