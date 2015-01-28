using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace LongestString
{
    /*
           Given a list of strings (single words or not), write a method to return the longest, n-th string contained in the list. The method signature is provided below:

private IList<string> getLongestString(int nTh, List<string> input){
               If more than one string is of the same length and is the n-th longest, return a collection
     */
    class Program
    {

        //solution: look at the variables in the Main function for unit test results
        static void Main(string[] args)
        {
            System.Diagnostics.Debug.WriteLine("The n-th longgest string is " + getLongestStringUnique(3, new List<string> { "12", "1", "", "12345678", "12345", "123" }));
            //tested nTh 3,5,6
            IList<string> Sixth = getLongestString(6, new List<string> { "12", "1", "", "12345678", "12345", "123", "12345678", "12345678", string.Empty,string.Empty });
            //tested nTh 2,6
            IList<string> Second = getLongestString(2, new List<string> { "12", "1", "", "12345678", "123", "12345", "123", "12345678", "12345678" });
            //tested nTh 3
            IList<string> Third = getLongestString(3, new List<string> { "12", "1", "", "12345678", "123", "12345", "123", "12345678", "12345678" });
            System.Diagnostics.Debugger.Break();
        }

        public static string getLongestStringUnique(int nTh, List<string> input)
        {
            input.Sort(delegate(string x, string y)
            {
                if (x.Length == y.Length)
                    return 0;
                else if (x.Length > y.Length)
                    return -1;
                else return 1;
            });

            return input[nTh - 1];
        }

        private static IList<string> getLongestString(int nTh, List<string> input)
        {
            input.Sort(delegate(string x, string y)
            {
                if (x.Length == y.Length)
                    return 0;
                else if (x.Length > y.Length)
                    return -1;
                else return 1;
            });

            List<int> Lengths = new List<int>();
            foreach (string s in input)
            {
                Lengths.Add(s.Length);
            }

            int n = nTh - 1;
            int i = 0;
            while (n > 0 && i + 1 <= Lengths.Count - 1)
            {
                if (Lengths[i] != Lengths[i + 1])
                {
                    --n;
                }
                ++i;
            }

            List<string> ret = new List<string>();

            ret.Add(input[i]);
            while (i < Lengths.Count - 1 && Lengths[i] == Lengths[i + 1])
            {
                ret.Add(input[i + 1]);
                ++i;
            }
            return ret;
        }
    }
}