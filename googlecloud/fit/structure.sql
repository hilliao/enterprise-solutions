-- phpMyAdmin SQL Dump
-- version 4.5.4.1deb2ubuntu2
-- http://www.phpmyadmin.net
--
-- Host: localhost
-- Generation Time: Jan 17, 2019 at 03:44 AM
-- Server version: 5.7.18-0ubuntu0.16.04.1
-- PHP Version: 7.0.18-0ubuntu0.16.04.1

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `fit`
--
CREATE DATABASE IF NOT EXISTS `fit` DEFAULT CHARACTER SET latin1 COLLATE latin1_swedish_ci;
USE `fit`;

-- --------------------------------------------------------

--
-- Table structure for table `activity`
--

CREATE TABLE IF NOT EXISTS `activity` (
  `username` varchar(255) NOT NULL,
  `day` varchar(255) NOT NULL,
  `activity_type` int(11) NOT NULL,
  `length_ms` int(11) NOT NULL,
  `n_segments` int(11) NOT NULL,
  `lastUpdated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`username`,`day`,`activity_type`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

-- --------------------------------------------------------

--
-- Table structure for table `activity_goals`
--

CREATE TABLE IF NOT EXISTS `activity_goals` (
  `username` varchar(255) NOT NULL,
  `minutes` int(11) NOT NULL,
  `lastModified` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

-- --------------------------------------------------------

--
-- Table structure for table `activity_types`
--

CREATE TABLE IF NOT EXISTS `activity_types` (
  `name` varchar(255) NOT NULL,
  `id` int(11) NOT NULL,
  `exercise` BOOL NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

--
-- Truncate table before insert `activity_types`
--

TRUNCATE TABLE `activity_types`;
--
-- Dumping data for table `activity_types`
--

INSERT INTO `activity_types` (`name`, `id`, `exercise`)
VALUES ('In vehicle*', 0, 0),
       ('Biking*', 1, 1),
       ('On foot*', 2, 0),
       ('Still (not moving)*', 3, 0),
       ('Unknown (unable to detect activity)*', 4, 0),
       ('Tilting (sudden device gravity change)*', 5, 0),
       ('Walking*', 7, 1),
       ('Running*', 8, 1),
       ('Aerobics', 9, 1),
       ('Badminton', 10, 1),
       ('Baseball', 11, 1),
       ('Basketball', 12, 1),
       ('Biathlon', 13, 1),
       ('Handbiking', 14, 1),
       ('Mountain biking', 15, 1),
       ('Road biking', 16, 1),
       ('Spinning', 17, 1),
       ('Stationary biking', 18, 1),
       ('Utility biking', 19, 1),
       ('Boxing', 20, 1),
       ('Calisthenics', 21, 1),
       ('Circuit training', 22, 1),
       ('Cricket', 23, 1),
       ('Dancing', 24, 1),
       ('Elliptical', 25, 1),
       ('Fencing', 26, 1),
       ('Football (American)', 27, 1),
       ('Football (Australian)', 28, 1),
       ('Football (Soccer)', 29, 1),
       ('Frisbee', 30, 1),
       ('Gardening', 31, 1),
       ('Golf', 32, 1),
       ('Gymnastics', 33, 1),
       ('Handball', 34, 1),
       ('Hiking', 35, 1),
       ('Hockey', 36, 1),
       ('Horseback riding', 37, 1),
       ('Housework', 38, 1),
       ('Jumping rope', 39, 1),
       ('Kayaking', 40, 1),
       ('Kettlebell training', 41, 1),
       ('Kickboxing', 42, 1),
       ('Kitesurfing', 43, 1),
       ('Martial arts', 44, 1),
       ('Meditation', 45, 1),
       ('Mixed martial arts', 46, 1),
       ('P90X exercises', 47, 1),
       ('Paragliding', 48, 1),
       ('Pilates', 49, 1),
       ('Polo', 50, 1),
       ('Racquetball', 51, 1),
       ('Rock climbing', 52, 1),
       ('Rowing', 53, 1),
       ('Rowing machine', 54, 1),
       ('Rugby', 55, 1),
       ('Jogging', 56, 1),
       ('Running on sand', 57, 1),
       ('Running (treadmill)', 58, 1),
       ('Sailing', 59, 1),
       ('Scuba diving', 60, 1),
       ('Skateboarding', 61, 1),
       ('Skating', 62, 1),
       ('Cross skating', 63, 1),
       ('Inline skating (rollerblading)', 64, 1),
       ('Skiing', 65, 1),
       ('Back-country skiing', 66, 1),
       ('Cross-country skiing', 67, 1),
       ('Downhill skiing', 68, 1),
       ('Kite skiing', 69, 1),
       ('Roller skiing', 70, 1),
       ('Sledding', 71, 1),
       ('Sleeping', 72, 1),
       ('Snowboarding', 73, 1),
       ('Snowmobile', 74, 1),
       ('Snowshoeing', 75, 1),
       ('Squash', 76, 1),
       ('Stair climbing', 77, 1),
       ('Stair-climbing machine', 78, 1),
       ('Stand-up paddleboarding', 79, 1),
       ('Strength training', 80, 1),
       ('Surfing', 81, 1),
       ('Swimming', 82, 1),
       ('Swimming (swimming pool)', 83, 1),
       ('Swimming (open water)', 84, 1),
       ('Table tennis (ping pong)', 85, 1),
       ('Team sports', 86, 1),
       ('Tennis', 87, 1),
       ('Treadmill (walking or running)', 88, 1),
       ('Volleyball', 89, 1),
       ('Volleyball (beach)', 90, 1),
       ('Volleyball (indoor)', 91, 1),
       ('Wakeboarding', 92, 1),
       ('Walking (fitness)', 93, 1),
       ('Nording walking', 94, 1),
       ('Walking (treadmill)', 95, 1),
       ('Waterpolo', 96, 1),
       ('Weightlifting', 97, 1),
       ('Wheelchair', 98, 1),
       ('Windsurfing', 99, 1),
       ('Yoga', 100, 1),
       ('Zumba', 101, 1),
       ('Diving', 102, 1),
       ('Ergometer', 103, 1),
       ('Ice skating', 104, 1),
       ('Indoor skating', 105, 1),
       ('Curling', 106, 1),
       ('Other (unclassified fitness activity)', 108, 1),
       ('Light sleep', 109, 0),
       ('Deep sleep', 110, 0),
       ('REM sleep', 111, 0),
       ('Awake (during sleep cycle)', 112, 0),
       ('Crossfit', 113, 1),
       ('HIIT', 114, 1),
       ('Interval Training', 115, 1),
       ('Walking (stroller)', 116, 1),
       ('Elevator', 117, 1),
       ('Escalator', 118, 1),
       ('Archery', 119, 1),
       ('Softball', 120, 1);

-- --------------------------------------------------------

--
-- Table structure for table `google_fit`
--

CREATE TABLE IF NOT EXISTS `google_fit` (
  `username` varchar(255) NOT NULL,
  `google_id` varchar(255) NOT NULL,
  `full_name` varchar(255) NOT NULL,
  `gender` varchar(255) DEFAULT NULL,
  `image_url` varchar(255) NOT NULL,
  `email` varchar(255) NOT NULL,
  `refresh_token` varchar(255) NOT NULL,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`google_id`),
  KEY `google_id` (`google_id`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

-- --------------------------------------------------------

--
-- Table structure for table `steps`
--

CREATE TABLE IF NOT EXISTS `steps` (
  `username` varchar(255) NOT NULL,
  `day` varchar(255) NOT NULL,
  `steps` int(11) NOT NULL,
  `lastUpdated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`username`,`day`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
