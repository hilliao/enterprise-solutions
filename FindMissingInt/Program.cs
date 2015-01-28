using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace FindMissingInt
{
    /*
       Given a list of numbers between some start and end value (i.e. in a specific range), where all the numbers in that range are present except for one, find the missing number

Ex: 
       [1,5,2,3]
       Range is between 1 and 5
       Missing number to  be returned is 4

       private int findMissing(int[] input){
    */
    class Program
    {

        //solution: look at the found variable in each line by stepping over them in Main method for unit test results. 
        static void Main(string[] args)
        {
            int? found;
            found = FindMissing(new int[] { 1, 5, 2, 3 });
            System.Diagnostics.Debugger.Break();
            found = FindMissing(new int[] { 1, 5, 2, 3, 0 });
            found = FindMissing(new int[] { 1, 5, 2, 3, 6, 7 });
            found = FindMissing(new int[] { 1, 5, 2, 3, 4, 6, 7, 8, 9, 0 });//null means no missing
            found = FindMissing(new int[] { 1, 5, 2, 3, 0, -1, 4, 7, 8 });
        }

        public static int? FindMissing(int[] input)
        {
            Array.Sort<int>(input);
            for (int i = 0; i < input.Length - 1; i++)
            {
                if (input[i + 1] != input[i] + 1)//found missing
                    return input[i] + 1;
            }
            return null;
        }
    }
}